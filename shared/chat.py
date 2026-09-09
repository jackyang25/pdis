"""Provider-neutral chat output; provider continuation is opaque to services.

Continuation lives only in one request's working conversation. It is neither
browser state nor a server session, and only its provider adapter interprets it.
"""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class ChatTurn:
    text: str
    tool_calls: tuple[ToolCall, ...]
    continuation: Any


@dataclass(frozen=True)
class ChatDelta:
    """Text as it arrives, followed by exactly one completed turn."""

    text: str = ""
    turn: ChatTurn | None = None
