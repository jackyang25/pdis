"""Searcher - web and literature retrieval service.

Public contract: consumers import from this package root only.
Internals (`stages/`, helpers) are not part of the contract.

Searcher can union OpenAI web_search findings with NCBI PubMed/PMC
literature findings. The public surface below is the wire protocol -
keep it small and stable.
"""

from .models import (
    Finding,
    SearcherLLMClientProtocol,
    findings_to_dicts,
)
from .net import prefer_ipv4
from .pipeline import run_pipeline
from .stages.searcher import DEFAULT_MAX_TOKENS, DEFAULT_MAX_USES

# Make the direct-HTTP lanes (PubMed, ClinicalTrials.gov) resilient in
# IPv6-less containers - see net.py. Cheap, idempotent, applied on import.
prefer_ipv4()

__all__ = [
    "DEFAULT_MAX_TOKENS",
    "DEFAULT_MAX_USES",
    "Finding",
    "SearcherLLMClientProtocol",
    "findings_to_dicts",
    "run_pipeline",
]
