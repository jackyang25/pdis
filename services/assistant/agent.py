"""Ask assistant: a read-only, grounded, hand-rolled agent loop (no framework).

Given a result object + its type + the conversation so far, it answers the
user's latest question using ONLY the result and the full text behind sources
already cited in it. It navigates the result with the generic tools in
`navigator` and never runs a fresh web search or mutates anything.

The loop is deliberately tiny: call the LLM with tools -> run any requested
tool over the result -> append the output -> repeat until the LLM answers.
"""

from __future__ import annotations

import json
import logging
from types import SimpleNamespace
from typing import Any, Iterator, Protocol

from . import document as document_reader
from . import navigator
from .legends import legend_for

logger = logging.getLogger(__name__)

DEFAULT_MAX_TOKENS = 4000
MAX_STEPS = 6


class ChatLLMProtocol(Protocol):
    """Tool-calling chat contract (satisfied by the shared OpenAIClient.chat)."""

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 4000,
    ) -> Any:
        ...


class StreamingChatLLMProtocol(ChatLLMProtocol, Protocol):
    """Ask streaming contract (satisfied by OpenAIClient.chat_stream)."""

    def chat_stream(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 4000,
    ) -> Iterator[Any]:
        ...


TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get",
            "description": "Return the JSON subtree at a dotted/indexed path, e.g. 'matches[3].insight' or 'section_grades[2].dimensions.rigor'. Use the overview to find paths.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "Path into the result, '' for the whole result."}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_document",
            "description": "Find source-document blocks whose heading or content contains a keyword. Returns exact block IDs and snippets; use before read_document when you do not know the block IDs.",
            "parameters": {
                "type": "object",
                "properties": {"keyword": {"type": "string"}},
                "required": ["keyword"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_document",
            "description": "Read exact parsed source-document blocks by ID. For a very large block, follow the returned next start_char to continue reading it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "block_ids": {"type": "array", "items": {"type": "string"}},
                    "start_char": {"type": "integer", "minimum": 0},
                },
                "required": ["block_ids"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_document_range",
            "description": "Read an ordered range of blocks from one source document. Use for broad review or summarization; follow the returned next start value to continue.",
            "parameters": {
                "type": "object",
                "properties": {
                    "doc_id": {"type": "string"},
                    "start": {"type": "integer", "minimum": 0},
                    "count": {"type": "integer", "minimum": 1, "maximum": 25},
                },
                "required": ["doc_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find",
            "description": "Return paths whose key or value contains a keyword (case-insensitive). Use to locate where something lives before get().",
            "parameters": {
                "type": "object",
                "properties": {"keyword": {"type": "string"}},
                "required": ["keyword"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_source",
            "description": "Open the FULL text behind a source URL that is ALREADY cited in the result (the stored excerpt is capped). Only URLs present in the result are allowed; this never runs a new web search.",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
            },
        },
    },
]


def answer(
    client: ChatLLMProtocol,
    result: dict[str, Any],
    result_type: str,
    messages: list[dict[str, Any]],
    *,
    document: list[dict[str, Any]] | None = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> str:
    """Answer the latest user turn. `messages` is the prior conversation
    (roles user/assistant); the system prompt + tool loop are added here.

    `document` is the source document behind the result (parsed blocks). A map
    is placed in the system prompt; exact text stays available through bounded
    document navigation tools."""
    allowed_urls = navigator.collect_urls(result)
    work = _initial_messages(result, result_type, messages, document)

    for _ in range(MAX_STEPS):
        message = client.chat(work, tools=TOOLS, max_tokens=max_tokens)
        if message is None:
            return "Sorry - I couldn't generate a response."
        tool_calls = getattr(message, "tool_calls", None)
        if not tool_calls:
            return getattr(message, "content", "") or ""

        work.append(_assistant_msg(message, tool_calls))
        for call in tool_calls:
            work.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": _run_tool(call, result, allowed_urls, document),
                }
            )

    # Out of tool budget: force a final grounded answer with no further tools.
    work.append({"role": "user", "content": "Answer now using what you've gathered."})
    message = client.chat(work, max_tokens=max_tokens)
    return (getattr(message, "content", "") or "") if message else ""


def answer_stream(
    client: StreamingChatLLMProtocol,
    result: dict[str, Any],
    result_type: str,
    messages: list[dict[str, Any]],
    *,
    document: list[dict[str, Any]] | None = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> Iterator[str]:
    """Stream the final grounded answer while keeping tool turns server-side.

    OpenAI emits function-call deltas before their arguments. Those turns are
    accumulated, executed, and appended to the private working conversation.
    Text-only turns are forwarded immediately to the caller.
    """
    allowed_urls = navigator.collect_urls(result)
    work = _initial_messages(result, result_type, messages, document)

    for _ in range(MAX_STEPS):
        content_parts: list[str] = []
        tool_parts: dict[int, dict[str, str]] = {}
        emitted_text = False

        for chunk in client.chat_stream(work, tools=TOOLS, max_tokens=max_tokens):
            choices = getattr(chunk, "choices", [])
            if not choices:
                continue
            delta = getattr(choices[0], "delta", None)
            if delta is None:
                continue

            for fragment in getattr(delta, "tool_calls", None) or []:
                index = getattr(fragment, "index", 0) or 0
                part = tool_parts.setdefault(
                    index,
                    {"id": "", "name": "", "arguments": ""},
                )
                call_id = getattr(fragment, "id", None)
                if call_id:
                    part["id"] = call_id
                function = getattr(fragment, "function", None)
                name = getattr(function, "name", None) if function else None
                arguments = getattr(function, "arguments", None) if function else None
                if name:
                    part["name"] += name
                if arguments:
                    part["arguments"] += arguments

            content = getattr(delta, "content", None)
            if content:
                content_parts.append(content)
                # Function-call turns normally contain no visible text. If a
                # model emits a short preamble first, forwarding it is still
                # preferable to delaying every normal answer until completion.
                if not tool_parts:
                    emitted_text = True
                    yield content

        tool_calls = _assembled_tool_calls(tool_parts)
        if not tool_calls:
            if not emitted_text:
                yield "Sorry - I couldn't generate a response."
            return

        if emitted_text:
            logger.warning("Assistant emitted text before a tool call; continuing the grounded turn.")
        work.append(
            _assistant_msg(
                SimpleNamespace(content="".join(content_parts)),
                tool_calls,
            )
        )
        for call in tool_calls:
            work.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": _run_tool(call, result, allowed_urls, document),
                }
            )

    work.append({"role": "user", "content": "Answer now using what you've gathered."})
    emitted_text = False
    for chunk in client.chat_stream(work, max_tokens=max_tokens):
        choices = getattr(chunk, "choices", [])
        if not choices:
            continue
        delta = getattr(choices[0], "delta", None)
        content = getattr(delta, "content", None) if delta else None
        if content:
            emitted_text = True
            yield content
    if not emitted_text:
        yield "Sorry - I couldn't generate a response."


def _assembled_tool_calls(parts: dict[int, dict[str, str]]) -> list[Any]:
    """Turn streamed tool-call fragments into the shape used by _run_tool."""
    return [
        SimpleNamespace(
            id=part["id"] or f"tool-{index}",
            function=SimpleNamespace(
                name=part["name"],
                arguments=part["arguments"],
            ),
        )
        for index, part in sorted(parts.items())
        if part["name"]
    ]


def _run_tool(
    call: Any,
    result: dict[str, Any],
    allowed_urls: set[str],
    document: list[dict[str, Any]] | None = None,
) -> str:
    name = call.function.name
    try:
        args = json.loads(call.function.arguments or "{}")
    except json.JSONDecodeError:
        return "Invalid tool arguments."
    if name == "get":
        return navigator.get(result, str(args.get("path", "")))
    if name == "find":
        return navigator.find(result, str(args.get("keyword", "")))
    if name == "find_document":
        if not document:
            return "Source document unavailable."
        return document_reader.find(document, str(args.get("keyword", "")))
    if name == "read_document":
        if not document:
            return "Source document unavailable."
        raw_ids = args.get("block_ids", [])
        block_ids = raw_ids if isinstance(raw_ids, list) else []
        start_char = args.get("start_char", 0)
        return document_reader.get(
            document,
            block_ids,
            start_char=start_char if isinstance(start_char, int) else 0,
        )
    if name == "read_document_range":
        if not document:
            return "Source document unavailable."
        start = args.get("start", 0)
        count = args.get("count", 25)
        return document_reader.get_range(
            document,
            str(args.get("doc_id", "")),
            start=start if isinstance(start, int) else 0,
            count=count if isinstance(count, int) else 25,
        )
    if name == "fetch_source":
        return navigator.fetch_source(str(args.get("url", "")), allowed_urls)
    return f"Unknown tool: {name}"


def _assistant_msg(message: Any, tool_calls: Any) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": getattr(message, "content", "") or "",
        "tool_calls": [
            {
                "id": c.id,
                "type": "function",
                "function": {"name": c.function.name, "arguments": c.function.arguments},
            }
            for c in tool_calls
        ],
    }


def _initial_messages(
    result: dict[str, Any],
    result_type: str,
    messages: list[dict[str, Any]],
    document: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    work: list[dict[str, Any]] = [
        {"role": "system", "content": _system_prompt(result, result_type, document)}
    ]
    visuals: list[dict[str, Any]] = []
    for block in document or []:
        image = block.get("image")
        if not isinstance(image, dict):
            continue
        media_type = str(image.get("media_type") or "")
        data = str(image.get("data_base64") or "")
        if not media_type or not data:
            continue
        visuals.extend(
            [
                {
                    "type": "text",
                    "text": f"Source-document visual for block [{block.get('id', '')}]:",
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{media_type};base64,{data}",
                        "detail": "high",
                    },
                },
            ]
        )
    if visuals:
        work.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Reference material only: these are source-document visuals "
                            "labeled by their exact block IDs. Use them with the parsed "
                            "text when answering the user's final question."
                        ),
                    },
                    *visuals,
                ],
            }
        )
    work.extend(messages)
    return work


def _system_prompt(
    result: dict[str, Any],
    result_type: str,
    document: list[dict[str, Any]] | None = None,
) -> str:
    has_doc = bool(document)
    is_workspace = result_type == "workspace"
    subject = (
        "the client-held workspace catalog and its available final analysis results"
        if is_workspace
        else "ONE analysis result the user just produced"
    )
    grounding = (
        "the full text behind sources it already cites"
        + (", and every parsed text or visual block in the SOURCE DOCUMENT" if has_doc else "")
    )
    two_sources = (
        "\n\nDOCUMENT ACCESS - IMPORTANT:\n"
        "- You DO have direct access to every parsed source-document block through "
        "find_document and read_document.\n"
        "- You may inspect, quote, compare, and cite parsed text and retained visuals using their block IDs.\n"
        "- Never claim that you can only see the analysis result or cannot inspect arbitrary "
        "document passages. You can inspect all parsed text through those tools.\n"
        "- Be precise about the boundary: you have the parsed document content, not the original "
        "binary file; parsed text and extracted visuals are preserved, while other formatting may not be.\n\n"
        "TWO SOURCES, TWO ROLES - keep them distinct:\n"
        "- ANALYSIS RESULTS (and the web sources they cite) contain derived judgments and evidence.\n"
        "- The SOURCE DOCUMENT is the author's CLAIMS: what the document asserts, NOT verified. "
        "Never treat a document claim as established fact - attribute it ('the document states...').\n"
        "- Cross-comparison is the point: line the document's claims up against the result's "
        "evidence and say where they agree, differ, or go unaddressed.\n"
        if has_doc
        else ""
    )
    document_section = (
        "\n\nSOURCE DOCUMENT MAP (the author's claims; cite exact block IDs):\n"
        f"{document_reader.overview(document or [])}"
        if has_doc
        else ""
    )
    return (
        "You are Ask: a read-only assistant that answers questions about "
        f"{subject}. You are grounded: answer ONLY from this submitted context and "
        f"{grounding}. You never run new web searches and never change anything.\n\n"
        f"WHAT THIS CONTEXT IS:\n{legend_for(result_type)}\n\n"
        "HOW TO READ IT - use the tools:\n"
        "- get(path): read a result subtree. find(keyword): locate result paths. "
        "find_document(keyword): locate document blocks. read_document(block_ids): read exact "
        "document text. read_document_range(doc_id): scan an ordered document. "
        "fetch_source(url): open the "
        "FULL text of an already-cited URL when the stored excerpt is not enough.\n"
        "- Don't guess paths; use the OVERVIEW below and find() to locate things."
        + (" Use the document map and document tools whenever the answer depends on the upload." if has_doc else "")
        + two_sources
        + "\n\nRULES:\n"
        "- Ground every claim in the result, a fetched cited source"
        + (", or the source document" if has_doc else "")
        + ". If something isn't there, say so plainly - do not invent it.\n"
        "- Cite the source URL(s) for evidence-based answers so the user can click through.\n"
        "- Be concise and specific; quote the relevant values/paths.\n\n"
        f"OVERVIEW OF THIS CONTEXT:\n{navigator.overview(result)}"
        + document_section
    )
