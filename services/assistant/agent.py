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
from dataclasses import dataclass
from typing import Any, Iterator, Literal, Protocol

from . import document as document_reader
from . import knowledge
from . import navigator
from . import skills
from . import resources
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

@dataclass(frozen=True)
class Chunk:
    """One piece of the answer, and what kind it is.

    A reader waiting on a silent tool turn is told what is happening, and that
    is not part of the answer. Tagging it here rather than marking it inside the
    text means the two never have to be separated again downstream: the route
    frames each kind as its own event, and the client reads them apart.

    The label comes from the verb that declared it, so a capability added later
    cannot ship without one, and the line can never claim work that is not running.
    """

    kind: Literal["text", "activity"]
    text: str


from .registry import REGISTRY, TOOLS, ToolContext, _VERBS, held_result_types





def answer_stream(
    client: StreamingChatLLMProtocol,
    result: dict[str, Any],
    result_type: str,
    messages: list[dict[str, Any]],
    *,
    document: list[dict[str, Any]] | None = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> Iterator[Chunk]:
    """Stream the final grounded answer while keeping tool turns server-side.

    OpenAI emits function-call deltas before their arguments. Those turns are
    accumulated, executed, and appended to the private working conversation.
    Text-only turns are forwarded immediately to the caller.
    """
    allowed_urls = navigator.collect_urls(result)
    context = ToolContext(
        result=result,
        allowed_urls=allowed_urls,
        document=document,
        held_result_types=held_result_types(result),
    )
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
                    yield Chunk('text', content)

        tool_calls = _assembled_tool_calls(tool_parts)
        if not tool_calls:
            if not emitted_text:
                yield Chunk("text", "Sorry - I couldn't generate a response.")
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
            yield Chunk('activity', resources.activity_for(REGISTRY, call.function.name))
            work.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": _run_tool(call, context),
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
            yield Chunk('text', content)
    if not emitted_text:
        yield Chunk("text", "Sorry - I couldn't generate a response.")


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


def _run_tool(call: Any, context: ToolContext) -> str:
    """Route one model tool call to the verb that declared it."""
    verb = _VERBS.get(call.function.name)
    if verb is None:
        return f"Unknown tool: {call.function.name}"
    try:
        args = json.loads(call.function.arguments or "{}")
    except json.JSONDecodeError:
        return "Invalid tool arguments."
    if not isinstance(args, dict):
        return "Invalid tool arguments."
    return verb.handler(context, args)


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
    """Assemble the agent's instructions as named sections.

    Built as a list rather than one concatenation with inline conditionals: a
    reader can see what the agent is told and in what order, and a section can be
    changed without editing the middle of an expression. Empty sections drop out,
    so an absent document leaves no blank heading behind.
    """
    has_doc = bool(document)
    is_workspace = result_type == "workspace"
    subject = (
        "the client-held workspace catalog and its available final analysis results"
        if is_workspace
        else "ONE analysis result the user just produced"
    )
    grounding = (
        "the canonical public PDIS product documentation, the full text behind sources it already cites"
        + (", and every parsed text or visual block in the SOURCE DOCUMENT" if has_doc else "")
    )

    role = (
        "You are Ask: a read-only assistant that answers questions about "
        f"{subject}. You are grounded: answer ONLY from this submitted context and "
        f"{grounding}. You never run new web searches and never change anything."
    )

    context_meaning = f"WHAT THIS CONTEXT IS:\n{legend_for(result_type)}"

    # Generated from the registry: a hand-written list here once named tools that
    # had been renamed, so the agent was told about a world it did not have.
    reach = (
        "WHAT YOU CAN REACH:\n"
        f"{resources.inventory(REGISTRY)}\n"
        "- Don't guess paths; use the OVERVIEW below and find_result to locate things.\n"
        "- A workflow is a procedure you follow, never a finding you report. Read one "
        "when a question needs more than one analysis. If it needs a result this "
        "workspace does not hold, say which run is missing and ask the user to run it; "
        "you cannot run anything yourself."
        + (
            " Use the document map and document tools whenever the answer depends on the upload."
            if has_doc
            else ""
        )
    )

    document_access = (
        "DOCUMENT ACCESS - IMPORTANT:\n"
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
        "evidence and say where they agree, differ, or go unaddressed."
        if has_doc
        else ""
    )

    grounding_rules = (
        "GROUNDING:\n"
        "- Use product documentation for questions about PDIS tools, process, architecture, results, and terminology. "
        "Never present product documentation as evidence about an analyzed health product.\n"
        "- Ground every claim in product documentation, the result, or a fetched cited source"
        + (", or the source document" if has_doc else "")
        + ". If something isn't there, say so plainly - do not invent it.\n"
        # Every citation is a markdown link, so the renderer never has to recognise
        # one in prose. The scheme decides what it becomes: an external link, an
        # openable passage, or - for anything it does not know - plain text.
        "- Cite what a reader can check, always as a markdown link:\n"
        "    evidence: [what it shows](https://the-source-url)\n"
        # Angle brackets are required, not stylistic: a block ID carries the
        # document name, and a name with spaces is not a valid link destination
        # without them - markdown renders the raw syntax instead of a link.
        "    a document passage: [what it says](<block:EXACT-BLOCK-ID>)\n"
        "    a place in an analysis: `matches[3].insight` in backticks, not a link.\n"
        # The label and the destination do different jobs, and saying so works with
        # the model rather than against it: repeating a full block ID through a
        # table is unreadable, so it shortened both and the destination stopped
        # resolving. Naming a section is the readable choice and always was.
        "  The visible text is for the reader, so keep it short - a section or "
        "variable name. The destination is what opens, so it must be the exact ID "
        "as it appears in the context, in angle brackets, never shortened."
    )

    answering = (
        "ANSWERING:\n"
        # "Be concise" is unfalsifiable; leading with the answer is not.
        "- Lead with the answer, then its support. Never open by restating the question "
        "or explaining what a tool is.\n"
        # Only worth saying now that the assistant renders GitHub-flavoured markdown;
        # before that a table arrived as raw pipes.
        "- Use a table when comparing the same fields across several items (variables, "
        "sections, runs, documents). Use prose for a single finding or an explanation.\n"
        "- Be specific: quote the actual values rather than describing them."
    )

    workflows = (
        "WORKFLOWS AVAILABLE:\n"
        f"{skills.catalog(held_result_types(result))}\n"
        "Read one with read_skill before answering a question it covers."
    )

    overview = f"OVERVIEW OF THIS CONTEXT:\n{navigator.overview(result)}"

    product_docs = (
        "PRODUCT DOCUMENTATION MAP (public PDIS behavior and architecture; not analysis evidence):\n"
        f"{knowledge.overview()}"
    )

    document_map = (
        "SOURCE DOCUMENT MAP (the author's claims; cite exact block IDs):\n"
        f"{document_reader.overview(document or [])}"
        if has_doc
        else ""
    )

    sections = [
        role,
        context_meaning,
        reach,
        document_access,
        grounding_rules,
        answering,
        workflows,
        overview,
        product_docs,
        document_map,
    ]
    return "\n\n".join(section for section in sections if section)
