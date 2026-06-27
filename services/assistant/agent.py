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
from typing import Any, Protocol

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
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> str:
    """Answer the latest user turn. `messages` is the prior conversation
    (roles user/assistant); the system prompt + tool loop are added here."""
    allowed_urls = navigator.collect_urls(result)
    work: list[dict[str, Any]] = [
        {"role": "system", "content": _system_prompt(result, result_type)},
        *messages,
    ]

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
                    "content": _run_tool(call, result, allowed_urls),
                }
            )

    # Out of tool budget: force a final grounded answer with no further tools.
    work.append({"role": "user", "content": "Answer now using what you've gathered."})
    message = client.chat(work, max_tokens=max_tokens)
    return (getattr(message, "content", "") or "") if message else ""


def _run_tool(call: Any, result: dict[str, Any], allowed_urls: set[str]) -> str:
    name = call.function.name
    try:
        args = json.loads(call.function.arguments or "{}")
    except json.JSONDecodeError:
        return "Invalid tool arguments."
    if name == "get":
        return navigator.get(result, str(args.get("path", "")))
    if name == "find":
        return navigator.find(result, str(args.get("keyword", "")))
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


def _system_prompt(result: dict[str, Any], result_type: str) -> str:
    return (
        "You are Ask: a read-only assistant that answers questions about ONE analysis "
        "result the user just produced. You are grounded: answer ONLY from this result and "
        "the full text behind sources it already cites. You never run new web searches and "
        "never change anything.\n\n"
        f"WHAT THIS RESULT IS:\n{legend_for(result_type)}\n\n"
        "HOW TO READ IT - use the tools:\n"
        "- get(path): read a subtree. find(keyword): locate paths. fetch_source(url): open the "
        "FULL text of an already-cited URL when the stored excerpt is not enough.\n"
        "- Don't guess paths; use the OVERVIEW below and find() to locate things.\n\n"
        "RULES:\n"
        "- Ground every claim in the result (or a fetched cited source). If something isn't in "
        "the results, say so plainly - do not invent it.\n"
        "- Cite the source URL(s) for evidence-based answers so the user can click through.\n"
        "- Be concise and specific; quote the relevant values/paths.\n\n"
        f"OVERVIEW OF THIS RESULT:\n{navigator.overview(result)}"
    )
