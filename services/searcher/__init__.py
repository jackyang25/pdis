"""Searcher - OpenAI web-search service.

Public contract: consumers import from this package root only.
Internals (`stages/`, helpers) are not part of the contract.

Today this is a Python package consumed by other services in-process.
The public surface below is the wire protocol - keep it small and stable.
"""

from .models import (
    Finding,
    SearcherLLMClientProtocol,
    findings_to_dicts,
)
from .pipeline import run_pipeline
from .stages.searcher import DEFAULT_MAX_TOKENS, DEFAULT_MAX_USES

__all__ = [
    "DEFAULT_MAX_TOKENS",
    "DEFAULT_MAX_USES",
    "Finding",
    "SearcherLLMClientProtocol",
    "findings_to_dicts",
    "run_pipeline",
]
