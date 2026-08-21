"""Static source registry.

Provider capabilities are engineering code, so registration is explicit and
reviewable. Product configs choose which registered keys are enabled per run.
"""

from .base import SourceAdapter
from .chembl import ChEMBLSource
from .clinicaltrials import ClinicalTrialsSource
from .ctis import CTISSource
from .fda import FDASource
from .fda_safety import FDASafetySource
from .isrctn import ISRCTNSource
from .open_targets import OpenTargetsSource
from .pubmed import PubMedSource
from .europepmc import EuropePMCSource
from .semantic_scholar import SemanticScholarSource
from .who_gho import WHOGHOSource
from .who_guidelines import WHOGuidelinesSource
from .web import WebSource

_SOURCES: tuple[SourceAdapter, ...] = (
    WebSource(),
    PubMedSource(),
    ClinicalTrialsSource(),
    CTISSource(),
    ISRCTNSource(),
    SemanticScholarSource(),
    EuropePMCSource(),
    WHOGuidelinesSource(),
    WHOGHOSource(),
    OpenTargetsSource(),
    ChEMBLSource(),
    FDASource(),
    FDASafetySource(),
)

SOURCE_REGISTRY: dict[str, SourceAdapter] = {
    source.spec.key: source for source in _SOURCES
}

__all__ = ["SOURCE_REGISTRY", "SourceAdapter"]
