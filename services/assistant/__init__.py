"""Reads over finished results: a grounded chat assistant, and one priority reading.

Public contract: consumers import from this package root only — `answer_stream`, its
`Chunk`, the `StreamingChatLLMProtocol` a client must satisfy, `limits` (every cap the
assistant enforces, which the API's request checks read), and the priority reading names.
Both readers are result-agnostic — chat navigates a result as a JSON tree (navigator) and
reads its meaning from a per-type legend (legends), and the priority reading is handed the
authority sentence and findings its caller already publishes. Neither mutates state, runs a tool, or
searches the web.
"""

from . import limits
from .agent import Chunk, answer_stream
from .priorities import (
    PriorityFinding,
    PriorityPoint,
    PriorityReading,
    PriorityRequest,
    PriorityRequestTooLarge,
    read_priorities,
)
from .protocols import StreamingChatLLMProtocol

__all__ = [
    "Chunk",
    "PriorityFinding",
    "PriorityPoint",
    "PriorityReading",
    "PriorityRequest",
    "PriorityRequestTooLarge",
    "StreamingChatLLMProtocol",
    "answer_stream",
    "limits",
    "read_priorities",
]
