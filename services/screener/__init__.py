"""Screener — stage-gate question triage across a set of product-development documents.

A gate review asks a fixed bank of SME questions. Screener does not answer them: it
reports what the documents answer, partly answer, or leave unanswered, alongside the
discipline that owns each question.

Its authority is the gate's question bank, which is what separates it from
Inspector. Inspector asks whether one document is complete against its own
template; Screener asks whether the evidence exists anywhere in the set for a
reviewer to close a question. Neither substitutes for the other.
"""

from .contract import validate_result_contract
from .models import (
    MODEL_STATES,
    QUESTION_STATES,
    DisciplineReview,
    DisciplineSpec,
    DocumentInput,
    GateConfig,
    GateReview,
    GateSpec,
    LLMClientProtocol,
    QuestionAssessment,
    QuestionResolution,
    QuestionSpec,
    QuestionState,
    ReviewDocument,
    available_configs,
    available_gates,
    find_config,
    has_config,
    load_config,
    resolve_questions,
)
from .pipeline import DEFAULT_MAX_OUTPUT_TOKENS, SUPPORTED_DOCUMENT_SUFFIXES, run_pipeline

__all__ = [
    "DEFAULT_MAX_OUTPUT_TOKENS",
    "SUPPORTED_DOCUMENT_SUFFIXES",
    "DisciplineReview",
    "DisciplineSpec",
    "DocumentInput",
    "GateConfig",
    "GateReview",
    "GateSpec",
    "LLMClientProtocol",
    "MODEL_STATES",
    "QUESTION_STATES",
    "QuestionAssessment",
    "QuestionResolution",
    "QuestionSpec",
    "QuestionState",
    "ReviewDocument",
    "available_configs",
    "available_gates",
    "find_config",
    "has_config",
    "load_config",
    "resolve_questions",
    "run_pipeline",
    "validate_result_contract",
]
