"""Expert — stage-gate question triage across a set of product-development documents.

A gate review asks a fixed bank of SME questions. Expert does not answer them: it
sorts them into what the documents already answer with a citation, what they should
answer and do not, and what no document could ever answer — those routed to the
discipline that owns them.

Its authority is the gate's question bank, which is what separates it from
Inspector. Inspector asks whether one document is complete against its own
template; Expert asks whether the evidence exists anywhere in the set for a
reviewer to close a question. Neither substitutes for the other.
"""

from .contract import validate_result_contract
from .models import (
    ANSWER_SOURCES,
    MODEL_STATES,
    QUESTION_STATES,
    AnswerSource,
    ContextItem,
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
    available_gates,
    find_config,
    has_config,
    load_config,
    resolve_questions,
)
from .pipeline import DEFAULT_MAX_OUTPUT_TOKENS, run_pipeline

__all__ = [
    "ANSWER_SOURCES",
    "AnswerSource",
    "ContextItem",
    "DEFAULT_MAX_OUTPUT_TOKENS",
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
    "available_gates",
    "find_config",
    "has_config",
    "load_config",
    "resolve_questions",
    "run_pipeline",
    "validate_result_contract",
]
