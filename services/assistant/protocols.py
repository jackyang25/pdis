"""What the Assistant needs from a model client: one streamed, tool-capable turn."""

from __future__ import annotations

from typing import Any, Iterator, Protocol

from shared.chat import ChatDelta

from .limits import MAX_OUTPUT_TOKENS


class StreamingChatLLMProtocol(Protocol):
    """Satisfied by `shared.openai_client.OpenAIClient.chat_stream`."""

    def chat_stream(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = MAX_OUTPUT_TOKENS,
    ) -> Iterator[ChatDelta]:
        ...
