"""Typed provider failures.

A failed request is recorded on its outcome, and a saved result is read long after the
run, so the failure has to say two things a reader can act on: a machine-readable code
that groups failures by kind (a rate limit is not an outage), and the provider's own
message (which limit, which endpoint, which argument). Collapsing both into a
``RuntimeError`` string left only the second, and often not even that.
"""

from __future__ import annotations

#: Closed vocabulary of provider-failure codes. An adapter error that is none of these is
#: recorded as `adapter_error` by the controller.
RETRIEVAL_ERROR_CODES = frozenset(
    {
        "rate_limited",
        "http_error",
        "unavailable",
        "timeout",
        "invalid_response",
        # The provider answered, but with a failure of its own instead of records: a query
        # it refused, an error inside a successful envelope.
        "rejected",
        "not_configured",
    }
)


class RetrievalError(RuntimeError):
    """One provider call that failed, with its code beside the provider's message."""

    def __init__(
        self,
        provider: str,
        code: str,
        message: str,
        *,
        status: int | None = None,
    ) -> None:
        if code not in RETRIEVAL_ERROR_CODES:
            raise ValueError(f"unknown retrieval error code: {code}")
        self.provider = provider
        self.code = code
        self.status = status
        self.message = " ".join(message.split())
        prefix = f"{provider} HTTP {status}" if status else provider
        super().__init__(f"{prefix}: {self.message}" if self.message else prefix)
