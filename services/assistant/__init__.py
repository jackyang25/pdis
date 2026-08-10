"""Reads over finished results: a grounded chat assistant, and one bounded digest.

Public contract: consumers import from this package root only. Both readers are
result-agnostic — chat navigates a result as a JSON tree (navigator) and reads its meaning
from a per-type legend (legends), and the priority digest is handed the authority sentence
its caller already publishes. Neither mutates state, runs a tool, or searches the web.
"""

from .agent import Chunk, ChatLLMProtocol, StreamingChatLLMProtocol, answer_stream
from .priorities import (
    MAX_NOMINATIONS,
    Nomination,
    PriorityDigest,
    PriorityItemInput,
    PriorityRequest,
    read_priorities,
)

__all__ = [
    "Chunk",
    "ChatLLMProtocol",
    "MAX_NOMINATIONS",
    "Nomination",
    "PriorityDigest",
    "PriorityItemInput",
    "PriorityRequest",
    "StreamingChatLLMProtocol",
    "answer_stream",
    "read_priorities",
]
