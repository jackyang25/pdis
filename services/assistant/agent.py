"""Ask: a read-only, grounded agent loop over one request's workspace.

Build the index, send the bounded prompt, run any tools the model calls, repeat until it
answers. The loop knows nothing about what the tools do; the registry does.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Generator, Iterator, Literal

from shared.chat import ChatTurn

from . import limits, resources
from .document import VisualBudget
from .prompt import system_prompt
from .protocols import StreamingChatLLMProtocol
from .registry import TOOLS, VERBS, ToolContext, run_tool
from .workspace import build_index

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Chunk:
    """One piece of the answer, and what kind it is.

    A reader waiting on a silent tool turn is told what is happening, and that
    is not part of the answer. Tagging it here rather than marking it inside the
    text means the two never have to be separated again downstream: the route
    frames each kind as its own event, and the client reads them apart.

    The label comes from the verb that declared it, so a capability added later
    cannot ship without one, and the line can never claim work that is not running.

    An `offer` carries `data` instead of text: a proposal for the interface to render
    as a control (`offers.SearchOffer.to_event`), never prose for the reader.
    """

    kind: Literal["text", "activity", "offer"]
    text: str = ""
    data: dict[str, Any] | None = None


@dataclass
class QuestionStats:
    """What one question cost, logged as one line when it ends."""

    model_calls: int = 0
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    tools_called: list[str] = field(default_factory=list)
    visuals_viewed: int = 0
    visuals_withheld: int = 0

    def add(self, turn: ChatTurn) -> None:
        self.model_calls += 1
        self.input_tokens += turn.usage.input_tokens
        self.cached_input_tokens += turn.usage.cached_input_tokens
        self.output_tokens += turn.usage.output_tokens


def answer_stream(
    client: StreamingChatLLMProtocol,
    result: dict[str, Any],
    messages: list[dict[str, Any]],
    *,
    document: list[dict[str, Any]] | None = None,
    max_tokens: int = limits.MAX_OUTPUT_TOKENS,
) -> Iterator[Chunk]:
    """Stream the final grounded answer while keeping tool turns server-side."""
    index = build_index(result, document)
    context = ToolContext(index=index, budget=VisualBudget())
    work: list[dict[str, Any]] = [{"role": "system", "content": system_prompt(index)}, *messages]
    stats = QuestionStats()
    try:
        for _ in range(limits.MAX_STEPS):
            turn = yield from _stream_turn(client, work, TOOLS, max_tokens, stats)
            if not turn.tool_calls:
                return
            # The provider owns continuation syntax. Carry it back unchanged, within
            # this request only, so reasoning and tool-call lineage survive each step.
            work.append({"role": "assistant", "content": turn.text, "continuation": turn.continuation})
            for call in turn.tool_calls:
                yield Chunk("activity", resources.activity_for(VERBS, call.name))
                output = run_tool(call, context)
                stats.tools_called.append(call.name)
                while context.offers:
                    yield Chunk("offer", data=context.offers.pop(0).to_event())
                work.append({"role": "tool", "tool_call_id": call.id,
                             "content": output.text, "images": output.images})
        work.append({"role": "user", "content": "Answer now using what you've gathered."})
        turn = yield from _stream_turn(client, work, None, max_tokens, stats)
        if turn.tool_calls:
            raise RuntimeError("Assistant did not complete its final answer")
    finally:
        stats.visuals_viewed = context.budget.viewed
        stats.visuals_withheld = context.budget.withheld
        logger.info("assistant_question %s", json.dumps(asdict(stats)))


def _stream_turn(
    client: StreamingChatLLMProtocol,
    work: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    max_tokens: int,
    stats: QuestionStats,
) -> Generator[Chunk, None, ChatTurn]:
    turn = None
    for delta in client.chat_stream(work, tools=tools, max_tokens=max_tokens):
        if delta.text:
            yield Chunk("text", delta.text)
        if delta.turn is not None:
            turn = delta.turn
    if turn is None:
        raise RuntimeError("Assistant provider stream ended before completing a turn")
    stats.add(turn)
    return turn
