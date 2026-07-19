"""Static source registry.

Provider capabilities are engineering code, so registration is explicit and
reviewable. Product configs choose which registered keys are enabled per run.
"""

from .base import SourceAdapter
from .clinicaltrials import ClinicalTrialsSource
from .pubmed import PubMedSource
from .web import WebSource

_SOURCES: tuple[SourceAdapter, ...] = (
    WebSource(),
    PubMedSource(),
    ClinicalTrialsSource(),
)

SOURCE_REGISTRY: dict[str, SourceAdapter] = {
    source.spec.key: source for source in _SOURCES
}

__all__ = ["SOURCE_REGISTRY", "SourceAdapter"]
