"""Ask - a read-only, grounded chat assistant over any result object.

Public contract: consumers import from this package root only. The assistant is
result-agnostic - it navigates a result as a JSON tree (navigator) and reads its
meaning from a per-type legend (legends), so new doc types plug in with only a
legend entry. It never mutates state or runs fresh web searches.
"""

from .agent import ChatLLMProtocol, answer

__all__ = ["ChatLLMProtocol", "answer"]
