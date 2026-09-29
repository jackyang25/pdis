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
class Usage:
    """What one model call cost, as the provider reported it."""

    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True)
class LabelledImage:
    """One retained document visual, never separated from the block it belongs to."""

    block_id: str
    media_type: str
    data_base64: str

    @property
    def data_url(self) -> str:
        return f"data:{self.media_type};base64,{self.data_base64}"


@dataclass(frozen=True)
class ToolOutput:
    """What a tool returns: text, and any images the model asked to see."""

    text: str
    images: tuple[LabelledImage, ...] = ()


@dataclass(frozen=True)
class ChatTurn:
    text: str
    tool_calls: tuple[ToolCall, ...]
    continuation: Any
    usage: Usage = Usage()


@dataclass(frozen=True)
class ChatDelta:
    """Text as it arrives, followed by exactly one completed turn."""

    text: str = ""
    turn: ChatTurn | None = None
