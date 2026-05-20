"""Reviewer — rubric grading app.

Consumes services (chunker for parsing/labeling, evidence for claims) and
produces a ReviewResult per document. Public contract below; internals
(`stages/`, `cli.py`) are not part of the contract.
"""

from .models import (
    BatchReviewResult,
    ReviewConfig,
    ReviewResult,
    find_config,
    review_result_to_dict,
)
from .pipeline import (
    DEFAULT_MAX_OUTPUT_TOKENS,
    review_blocks,
    review_blocks_batch,
    run_pipeline,
    run_pipeline_batch,
)

__all__ = [
    "BatchReviewResult",
    "DEFAULT_MAX_OUTPUT_TOKENS",
    "ReviewConfig",
    "ReviewResult",
    "find_config",
    "review_blocks",
    "review_blocks_batch",
    "review_result_to_dict",
    "run_pipeline",
    "run_pipeline_batch",
]
