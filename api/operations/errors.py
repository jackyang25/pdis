"""Coded application failures for transport-specific error mapping."""

from __future__ import annotations


class OperationError(RuntimeError):
    """A safe application failure with a stable machine-readable code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
