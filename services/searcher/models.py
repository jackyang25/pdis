"""Searcher data shapes and the LLM client contract it requires.

Public types live here - they are re-exported by __init__.py. Consumers
should import from `services.searcher`, never from this module directly.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Protocol


@dataclass
class Finding:
    """One atomic, source-attributed result from a web search.

    Stays intentionally primitive. No synthesis, no relevance scores,
    no provenance fields beyond what's needed to cite and date the
    source. Consumers (e.g. a monitoring tool) layer their own
    reasoning on top.
    """

    url: str
    title: str
    excerpt: str
    query: str
    retrieved_at: datetime
    published_at: datetime | None = None


class SearcherLLMClientProtocol(Protocol):
    """Contract searcher requires from any injected LLM client.

    Library code depends only on this Protocol - the concrete client
    (AnthropicClient, a mock, anything) is passed in by the caller.
    """

    def search_web(self, query: str, *, max_tokens: int, max_uses: int) -> Any:
        ...


def findings_to_dicts(findings: list[Finding]) -> list[dict]:
    """Convert Finding objects to plain dictionaries (datetimes -> ISO strings)."""
    out: list[dict] = []
    for finding in findings:
        d = asdict(finding)
        d["retrieved_at"] = finding.retrieved_at.isoformat()
        d["published_at"] = (
            finding.published_at.isoformat() if finding.published_at else None
        )
        out.append(d)
    return out
