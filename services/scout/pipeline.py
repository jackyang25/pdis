"""Stateless scout pipeline.

Orchestrates: chunker (parse only) -> canonical target binding -> per-unit query
generation (LLM) -> lane-native retrieval routing -> searcher -> per-unit insight
extraction (LLM) -> four independent reasoning layers. Reuses chunker and
searcher through their public contracts only.
"""

from __future__ import annotations

import copy
from datetime import date
from pathlib import Path
from typing import Callable, TypeVar

from services.chunker import ContentBlock, run_pipeline as chunker_run
from services.searcher import (
    Finding,
    lane_class,
    SearchRequest,
    SearchRuntime,
    dedupe_findings,
    plan_requests,
    run_requests,
)

from .context import (
    document_block_ids,
    render_canonical_binding,
    render_document_context,
)
from .contract import require_field_selection, validate_result_contract
from .lineage import RetrievalLineage
from shared.batching import budgeted_batches, map_ordered
from shared.errors import ModelResponseError
from shared.source_blocks import image_inputs
from shared.vocabulary import search_term
from .models import (
    NOT_SEARCHED,
    PROGRAM_SCOPE_KEY,
    RetrievalScopeLedger,
    Attribute,
    ConformityScore,
    DocumentContextValidation,
    EvidenceAssessment,
    FunnelStats,
    IdentityReconciliation,
    Insight,
    LLMClientProtocol,
    Match,
    ScoutResult,
    ScoutTypeConfig,
    PrecedentSignal,
    QuantitativeLedger,
    QuantitativeTarget,
    QueryIntent,
    SearchTrace,
    load_attributes,
)
from .projections import (
    build_development_landscape,
    build_safety_observations,
)
from .stages.conformity import (
    assemble_quantitative_document_ledger,
    empty_conformity_scores,
    extract_quantitative_ledger_batch,
    finalize_quantitative_document_review,
    prepare_quantitative_ledger_batches,
    reconcile_quantitative_document_ledger,
    score_conformity_all,
)
from .stages.context_validator import mismatch_message, validate_document_context
from .stages.drift_classifier import classify_drift
from .stages.evidence_assessor import assess_evidence, no_evidence_assessment
from .stages.evidence_reviewer import prefill_evidence_review
from .stages.insight_extractor import extract_insights
from .stages.insight_reconciler import reconcile_duplicate_insights
from .stages.precedent_classifier import classify_precedent, no_evidence_precedent
from .stages.projection_classifier import classify_projection_relationships
from .stages.projection_reconciler import reconcile_projection_names
from .stages.announcement_reader import read_announcements
from .stages.scope_resolver import resolve_retrieval_scope
from .stages.query_extractor import extract_queries_for_variable
from .stages.intent_builder import build_program_intents, build_retrieval_intents
from .stages.target_resolver import resolve_document_targets
from .stages.target_reviewer import prefill_target_review
from .stages.unit_extractor import extract_units

#: Insight extraction reads one variable's findings in batches, because what it
#: produces is a statement about the set: one fact reported by a trial registry and by
#: the paper of its results is one insight citing both, and only a request holding
#: both can write it that way. Forty records, or fewer when their excerpts would pass
#: the character budget - Searcher's excerpts run to sixteen thousand characters, so
#: the budget, not the count, bounds a batch of full-text records.
FINDINGS_PER_REQUEST = 40
FINDINGS_CHARS_PER_REQUEST = 240_000
SEARCH_MAX_TOKENS = 8000

# Parallelism for Scout's LLM reasoning fan-outs. Retrieval concurrency belongs
# to each Searcher source adapter and is not duplicated here.
MAX_WORKERS = 32
QUANTITATIVE_EXTRACTION_WORKERS = 8


def run_pipeline(
    file_paths: list[str],
    *,
    doc_ids: list[str] | None = None,
    config: ScoutTypeConfig,
    openai_client: LLMClientProtocol,
    quantitative_mapping_client: LLMClientProtocol,
    retrieval_runtime: SearchRuntime,
    org: str,
    source_type: str,
    intervention_class: str,
    indication: str,
    published_since: str = "",
    progress_callback=None,
) -> ScoutResult:
    """Prepare one canonical, client-held document-target review draft.

    Retrieval intentionally does not begin here. The reviewed draft is passed
    to :func:`continue_pipeline`, keeping the service stateless while ensuring
    that no unreviewed numeric interpretation can shape search or statistics.
    """
    if progress_callback:
        progress_callback("parse")
    blocks = _parse_all_docs(
        file_paths,
        doc_ids=doc_ids,
        org=org,
        source_type=source_type,
        intervention_class=intervention_class,
        # The stored tag, not the search term: blocks carry provenance, and a saved
        # result has to keep the key its configuration was selected by.
        indication=indication,
    )
    # From here both tags only ever become text — query strings, prompt sentences, and
    # the context-validation notice a reader sees — so they are normalised once, upstream,
    # rather than at each of the eight places a stage interpolates them. That is what let
    # `group_b_streptococcus` reach a query as one underscored token, and what confined
    # the vocabulary to single words until it had to spell Group B Streptococcus `gbs`.
    # The class is the same kind of value and had the same fault: it reached retrieval as
    # `mab`, which is not what a literature search uses. Stages holding a config instead
    # of these arguments read `config.intervention_term`, which derives the same word.
    indication = search_term(indication)
    intervention_class = search_term(intervention_class)
    # Preserve block IDs through every doc-aware stage. The model may cite only
    # these markers; each stage validates returned IDs against its input context.
    doc_text = render_document_context(blocks)
    images = image_inputs(blocks) or None

    if progress_callback:
        progress_callback("context")
    context_validation = validate_document_context(
        doc_text,
        openai_client,
        indication=indication,
        images=images,
    )
    if context_validation.status == "mismatch":
        raise ValueError(mismatch_message(context_validation))

    reconciliations: list[IdentityReconciliation] = []
    attributes = _resolve_units(
        config, doc_text, openai_client, indication=indication, images=images,
        reconciliations=reconciliations, progress_callback=progress_callback,
    )
    if not attributes:
        return validate_result_contract(ScoutResult(
            matches=[],
            assessments=[],
            stats=_empty_stats(),
            context_validation=context_validation,
            blocks=blocks,
            published_since=published_since,
            retrieval_scope=_header_scope(indication, intervention_class),
            reconciliations=reconciliations,
        ))

    # Provider-specific work ends here. Fixed definitions are resolved in
    # bounded output batches that share the same document and complete field
    # catalog; dynamically extracted units arrive already bound. Every later
    # stage receives the same canonical Attribute contract.
    attributes = resolve_document_targets(
        attributes,
        doc_text,
        openai_client,
        images=images,
        progress_callback=(
            (lambda **counts: progress_callback("targets", **counts))
            if progress_callback else None
        ),
    )
    unresolved_attributes = [
        attribute
        for attribute in attributes
        if (
            not attribute.target_resolved
            or (
                bool(attribute.document_target)
                and not attribute.document_spans
            )
        )
    ]
    if unresolved_attributes:
        # Unresolved canonical fields stop retrieval. That is a failed run, not a
        # finished one: an empty final result would read as a review that found nothing.
        raise ModelResponseError(
            "Document claim resolution stopped before retrieval: "
            f"{len(unresolved_attributes)} field decision(s) remained unresolved after "
            "one bounded retry ("
            + ", ".join(attribute.name for attribute in unresolved_attributes)
            + ")."
        )

    # What the run will search for, resolved before review rather than in the
    # continuation: two layers read it - query generation, which needs the geography to
    # write queries about the right places, and the adapters, which filter by it - and a
    # reading that fails should stop the run before anyone reviews anything. Carried on
    # the draft, so the reviewer sees it and the continuation cannot re-read it.
    if progress_callback:
        progress_callback("scope")
    retrieval_scope = resolve_retrieval_scope(
        attributes,
        openai_client,
        condition=indication,
        intervention_class=intervention_class,
    )

    ledger_batches = prepare_quantitative_ledger_batches(blocks, attributes)

    def map_ledger_batch(batch):
        return extract_quantitative_ledger_batch(
            batch,
            attributes,
            quantitative_mapping_client,
            indication=indication,
            intervention_class=intervention_class,
            framing=config.quantitative_target_framing,
        )

    ledger_results = _parallel_map(
        ledger_batches,
        map_ledger_batch,
        workers=QUANTITATIVE_EXTRACTION_WORKERS,
        stage="quantitative_targets",
        progress=progress_callback,
    )
    attributes, quantitative_ledger = assemble_quantitative_document_ledger(
        attributes,
        ledger_batches,
        ledger_results,
    )
    # Identity, not mapping: OpenAI, as every identity layer is (AGENTS limits
    # Anthropic to target and measurement mapping).
    attributes, quantitative_ledger, reconciliation = reconcile_quantitative_document_ledger(
        attributes,
        quantitative_ledger,
        openai_client,
    )
    if reconciliation is not None:
        reconciliations.append(reconciliation)
    if progress_callback:
        progress_callback("target_review")
    attributes, quantitative_ledger = prefill_target_review(
        attributes,
        quantitative_ledger,
        blocks,
        openai_client,
        progress=_stage_counts(progress_callback, "target_review"),
    )
    return validate_result_contract(ScoutResult(
        matches=[],
        assessments=[],
        stats=_empty_stats(),
        context_validation=context_validation,
        quantitative_ledger=quantitative_ledger,
        variables=attributes,
        blocks=blocks,
        phase="target_review",
        # Declared before retrieval and carried through the review round-trip,
        # so the continuation searches the window the user actually chose.
        published_since=published_since,
        retrieval_scope=retrieval_scope,
        reconciliations=reconciliations,
    ))


def continue_pipeline(
    prepared: ScoutResult,
    *,
    config: ScoutTypeConfig,
    openai_client: LLMClientProtocol,
    quantitative_mapping_client: LLMClientProtocol,
    retrieval_runtime: SearchRuntime,
    org: str,
    source_type: str,
    intervention_class: str,
    indication: str,
    progress_callback=None,
) -> ScoutResult:
    """Continue from one explicitly reviewed, portable target draft.

    Only the fields the reviewer kept are searched: queries, retrieval, insights, every
    judging stage and calibration see those alone, and each field left out is recorded
    ``not_searched``. The program-wide questions still run, because they belong to no
    field - their answer is the same whichever fields were chosen.
    """
    validate_result_contract(prepared)
    require_field_selection(prepared)
    # Blocks arrive already stamped by the draft. Insights are stamped here, with the
    # stored tags kept below: a saved result keeps the key its configuration was
    # selected by. Every other use is text, normalised once as in `run_pipeline`.
    indication_tag, intervention_tag = indication, intervention_class
    indication = search_term(indication)
    intervention_class = search_term(intervention_class)
    if prepared.phase != "target_review":
        raise ValueError("Scout continuation requires a target-review draft")
    if prepared.retrieval_scope is None:
        raise ValueError("Scout continuation requires the draft's retrieval scope")
    blocks = prepared.blocks
    context_validation = prepared.context_validation
    retrieval_scope = prepared.retrieval_scope
    reconciliations = list(prepared.reconciliations)
    attributes, quantitative_ledger = finalize_quantitative_document_review(
        prepared.variables,
        prepared.quantitative_ledger,
    )
    not_searched = set(prepared.not_searched_fields)
    active_quantitative_targets = _calibrated_targets(quantitative_ledger, not_searched)
    # Numeric interpretation is load-bearing only for quantitative calibration.
    # An unresolved statement remains excluded from target-specific queries and
    # statistics, but it must not discard the already verified document-claim
    # ledger or prevent the independent qualitative evidence workflow.
    searchable_attributes = [
        attribute for attribute in _searchable(attributes)
        if attribute.name not in not_searched
    ]
    attribute_descriptions = {
        attribute.name: attribute.description for attribute in searchable_attributes
    }
    # The broader definition view has completed its bounded binding/semantic
    # jobs. Every later reasoning stage receives the canonical target with its
    # exact block markers, not the rest of a potentially multi-topic table row.
    attribute_contexts = {
        attribute.name: render_canonical_binding(attribute)
        for attribute in searchable_attributes
    }
    attribute_images = _images_for_contexts(attribute_contexts, blocks)

    def empty(**kwargs) -> ScoutResult:
        return _empty_result(
            blocks=blocks,
            variables=attributes,
            quantitative_ledger=quantitative_ledger,
            context_validation=context_validation,
            published_since=prepared.published_since,
            retrieval_scope=retrieval_scope,
            reconciliations=reconciliations,
            not_searched_fields=prepared.not_searched_fields,
            **kwargs,
        )

    if progress_callback:
        progress_callback("queries")
    attribute_queries = _extract_queries_all_variables(
        searchable_attributes,
        active_quantitative_targets,
        config,
        openai_client,
        query_contexts=attribute_contexts,
        indication=indication,
        scope=retrieval_scope,
        progress=progress_callback,
    )
    flat: list[tuple[str, QueryIntent]] = [
        (attribute_ref, query)
        for attribute_ref, queries in attribute_queries.items()
        for query in queries
    ]
    if not flat:
        return empty()

    if progress_callback:
        progress_callback("search")
    retrieval_intents = build_retrieval_intents(
        attribute_queries,
        searchable_attributes,
        scope=retrieval_scope,
        published_since=prepared.published_since,
    )
    search_tasks = plan_requests(retrieval_intents, sources=config.sources)
    # The run's own questions, planned against the lanes each set declares rather than
    # against every configured source. Appended to the same task list so they share one
    # execution, one date window and one deduplication pass - they are ordinary requests
    # that happen to carry a different scope.
    for program_intent, lanes in build_program_intents(
        retrieval_scope, published_since=prepared.published_since
    ):
        search_tasks += plan_requests([program_intent], sources=lanes)
    findings_by_attribute, total_findings, search_plan = _search_all(
        search_tasks,
        retrieval_runtime,
        published_since=prepared.published_since,
        progress=progress_callback,
    )
    if not findings_by_attribute:
        return empty(queries=len(flat), search_plan=search_plan)

    # Adapters own source-specific parsing. These views consume only normalized
    # records and therefore add no new model judgment or provider branch here.
    # Program-scoped findings are prose, so the record the landscape groups by has to be
    # read out of them. Before the landscape is built, and only for findings that carry
    # no record yet.
    announcements = read_announcements(
        findings_by_attribute.get(PROGRAM_SCOPE_KEY, []),
        openai_client,
        progress=_stage_counts(progress_callback, "announcements"),
    )
    # Which stated names are one program or product is decided once, by its own layer,
    # before either view groups by name.
    names, name_reconciliation = reconcile_projection_names(findings_by_attribute, openai_client)
    if name_reconciliation is not None:
        reconciliations.append(name_reconciliation)
    development_landscape = build_development_landscape(findings_by_attribute, names)
    safety_observations = build_safety_observations(findings_by_attribute, names)
    development_landscape, safety_observations = classify_projection_relationships(
        searchable_attributes,
        development_landscape,
        safety_observations,
        openai_client,
        indication=indication,
        intervention_class=intervention_class,
    )

    if progress_callback:
        progress_callback("insights")
    insights, insight_reconciliations = _extract_insights_all_variables(
        findings_by_attribute,
        attribute_descriptions,
        RetrievalLineage(search_tasks),
        openai_client,
        indication=indication,
        intervention_class=intervention_class,
        progress=progress_callback,
    )
    reconciliations.extend(insight_reconciliations)

    _stamp(
        insights,
        org=org,
        source_type=source_type,
        intervention_class=intervention_tag,
        indication=indication_tag,
    )

    if progress_callback:
        progress_callback("classify")
    matches = _classify_drift_all(
        attribute_contexts,
        insights,
        openai_client,
        indication=indication,
        intervention_class=intervention_class,
        framing=config.drift_framing,
        attribute_images=attribute_images,
        progress=progress_callback,
    )

    if progress_callback:
        progress_callback("evidence")
    assessments = _assess_evidence_all_variables(
        searchable_attributes,
        attribute_contexts,
        insights,
        openai_client,
        indication=indication,
        intervention_class=intervention_class,
        framing=config.evidence_framing,
        attribute_images=attribute_images,
        progress=progress_callback,
    )

    if progress_callback:
        progress_callback("conformity")
    conformity = _score_conformity_all_variables(
        searchable_attributes,
        active_quantitative_targets,
        insights,
        quantitative_mapping_client,
        indication=indication,
        intervention_class=intervention_class,
        progress=progress_callback,
    )
    if progress_callback:
        progress_callback("evidence_review")
    conformity = prefill_evidence_review(
        conformity,
        active_quantitative_targets,
        openai_client,
        progress=_stage_counts(progress_callback, "evidence_review"),
    )

    if progress_callback:
        progress_callback("precedent")
    precedents = _classify_precedent_all_variables(
        searchable_attributes,
        attribute_contexts,
        insights,
        openai_client,
        indication=indication,
        intervention_class=intervention_class,
        framing=config.precedent_framing,
        attribute_images=attribute_images,
        progress=progress_callback,
    )

    # The fields left out at review keep their records, in document order beside the rest.
    assessments = _with_not_searched(attributes, not_searched, assessments, _not_searched_assessment)
    precedents = _with_not_searched(attributes, not_searched, precedents, _not_searched_precedent)
    stats = FunnelStats(
        queries=len(flat),
        findings=total_findings,
        unique_findings=_unique_records(findings_by_attribute),
        insights=len(insights),
        matches=len(matches),
        assessments=len(assessments),
        announcements_read=announcements.read,
        announcements_named=announcements.named,
        announcements_failed=announcements.failed,
        announcements_failed_by_code=announcements.failed_by_code,
    )
    has_evidence_review = any(
        measurement.admission_status == "needs_review"
        for score in conformity
        for measurement in [*score.measurements, *score.excluded_measurements]
    )
    return validate_result_contract(ScoutResult(
        matches=matches,
        assessments=assessments,
        stats=stats,
        conformity=conformity,
        precedents=precedents,
        search_plan=search_plan,
        development_landscape=development_landscape,
        safety_observations=safety_observations,
        context_validation=context_validation,
        quantitative_ledger=quantitative_ledger,
        variables=attributes,
        blocks=blocks,
        phase="evidence_review" if has_evidence_review else "final",
        published_since=prepared.published_since,
        retrieval_scope=retrieval_scope,
        reconciliations=reconciliations,
        not_searched_fields=prepared.not_searched_fields,
    ))


def _searchable(attributes: list[Attribute]) -> list[Attribute]:
    """The attributes retrieval investigates: those with a bound, cited document target."""
    return [
        attribute
        for attribute in attributes
        if attribute.document_target and attribute.document_spans
    ]


def _not_searched_assessment(attribute: Attribute) -> EvidenceAssessment:
    """The grounding record for a field the reviewer left out: no search, so no reason."""
    return EvidenceAssessment(
        attribute_ref=attribute.name,
        strength=NOT_SEARCHED,
        doc_target=attribute.document_target,
        doc_block_ids=list(attribute.block_ids),
    )


def _not_searched_precedent(attribute: Attribute) -> PrecedentSignal:
    """The precedent record for a field the reviewer left out, on both axes."""
    return PrecedentSignal(
        attribute_ref=attribute.name,
        precedent=NOT_SEARCHED,
        outcome=NOT_SEARCHED,
        doc_block_ids=list(attribute.block_ids),
    )


_Record = TypeVar("_Record", EvidenceAssessment, PrecedentSignal)


def _with_not_searched(
    attributes: list[Attribute],
    not_searched: set[str],
    records: list[_Record],
    build: Callable[[Attribute], _Record],
) -> list[_Record]:
    """One record per searchable field, in document order: the searched fields' own, and a
    ``not_searched`` record for each field the reviewer excluded."""
    by_field = {record.attribute_ref: record for record in records}
    return [
        build(attribute) if attribute.name in not_searched else by_field[attribute.name]
        for attribute in _searchable(attributes)
        if attribute.name in not_searched or attribute.name in by_field
    ]


def _header_scope(indication: str, intervention_class: str) -> RetrievalScopeLedger:
    """The scope a run has before any attribute is bound: the header's two values."""
    return resolve_retrieval_scope(
        [], None, condition=indication, intervention_class=intervention_class,
    )


def _empty_stats() -> FunnelStats:
    return FunnelStats(
        queries=0, findings=0, unique_findings=0, insights=0, matches=0, assessments=0,
    )


def _unique_records(findings_by_attribute: dict[str, list[Finding]]) -> int:
    """How many distinct records the run retrieved, across every field."""
    return len(dedupe_findings(
        copy.copy(finding)
        for findings in findings_by_attribute.values()
        for finding in findings
    ))


def _resolve_units(
    config: ScoutTypeConfig,
    doc_text: str,
    openai_client: LLMClientProtocol,
    *,
    indication: str,
    images: list[dict[str, str]] | None,
    reconciliations: list[IdentityReconciliation],
    progress_callback: ProgressFn | None = None,
) -> list[Attribute]:
    """Get definitions from the configured provider.

    ``vocabulary`` reads fixed definitions; ``extract`` returns dynamically
    defined units already bound to their document targets, after their identity
    layer, whose record joins ``reconciliations``. The next stage binds fixed
    definitions so provider-specific semantics end before retrieval.
    """
    if config.unit_provider == "extract":
        units, record = extract_units(
            doc_text,
            intervention_class=config.intervention_term,
            source_type=config.source_type,
            indication=indication,
            llm_client=openai_client,
            progress_callback=progress_callback,
            images=images,
        )
        if record is not None:
            reconciliations.append(record)
        return units
    return load_attributes(config.intervention_class)


def _parse_all_docs(
    file_paths: list[str],
    *,
    doc_ids: list[str] | None = None,
    org: str,
    source_type: str,
    intervention_class: str,
    indication: str,
) -> list[ContentBlock]:
    """Parse each doc via chunker without section-label mapping."""
    if doc_ids is not None and len(doc_ids) != len(file_paths):
        raise ValueError("doc_ids must have the same length as file_paths")
    blocks: list[ContentBlock] = []
    for index, file_path in enumerate(file_paths):
        doc_id = doc_ids[index] if doc_ids is not None else Path(file_path).stem
        doc_blocks = chunker_run(
            file_path,
            doc_id,
            org=org,
            source_type=source_type,
            intervention_class=intervention_class,
            indication=indication,
        )
        blocks.extend(doc_blocks)
    return blocks


_T = TypeVar("_T")
_R = TypeVar("_R")

# A progress reporter: progress(stage, completed=int, total=int). Optional - when
# None, stages run with no per-item reporting. Threaded explicitly (never a
# global) so concurrent requests can't cross-report.
ProgressFn = Callable[..., None]


def _parallel_map(
    items: list[_T],
    fn: Callable[[_T], _R],
    *,
    workers: int,
    stage: str,
    progress: ProgressFn | None,
) -> list[_R]:
    """Run `fn` over `items` concurrently, preserving input order, emitting
    `progress(stage, completed, total)` from zero and as each task FINISHES."""
    if not items:
        return []
    if progress:
        progress(stage, completed=0, total=len(items))
    return map_ordered(
        items,
        fn,
        workers=workers,
        on_progress=_stage_counts(progress, stage),
    )


def _stage_counts(
    progress: ProgressFn | None, stage: str,
) -> Callable[[int, int], None] | None:
    """Adapt the run's progress reporter to a stage's `(completed, total)` hook."""
    if progress is None:
        return None
    return lambda completed, total: progress(stage, completed=completed, total=total)


def _extract_queries_all_variables(
    attributes: list[Attribute],
    quantitative_targets: list[QuantitativeTarget],
    config: ScoutTypeConfig,
    openai_client: LLMClientProtocol,
    *,
    query_contexts: dict[str, str],
    indication: str,
    scope: RetrievalScopeLedger,
    progress: ProgressFn | None = None,
) -> dict[str, list[QueryIntent]]:
    """Run query extraction across attribute variables with bounded concurrency."""
    if not attributes:
        return {}

    def one(attribute: Attribute) -> tuple[str, list[QueryIntent]]:
        return attribute.name, extract_queries_for_variable(
            attribute,
            quantitative_targets,
            config,
            openai_client,
            indication=indication,
            scope=scope,
            document_context=query_contexts.get(attribute.name, ""),
        )

    results = _parallel_map(
        attributes, one, workers=MAX_WORKERS, stage="queries", progress=progress
    )
    return {name: queries for name, queries in results if queries}


def _images_for_contexts(
    contexts: dict[str, str],
    blocks: list[ContentBlock],
) -> dict[str, list[dict[str, str]]]:
    """Attach visuals by the exact block IDs present in each bounded context."""
    return {
        attribute_ref: image_inputs(
            block for block in blocks if block.id in document_block_ids(context)
        )
        for attribute_ref, context in contexts.items()
    }


def _extract_insights_all_variables(
    findings_by_attribute: dict[str, list[Finding]],
    attribute_descriptions: dict[str, str],
    lineage: RetrievalLineage,
    openai_client: LLMClientProtocol,
    *,
    indication: str,
    intervention_class: str,
    progress: ProgressFn | None = None,
) -> tuple[list[Insight], list[IdentityReconciliation]]:
    """Run insight extraction concurrently across all (variable, finding-batch)
    units, then decide their identity once per field.

    Every evidence-role finding is retained; reference-role records are excluded
    because they carry catalog metadata rather than evidence. Batches are bounded
    by both item count and rendered character size so one unusually large source
    cannot crowd the model context. Each task remains single-variable; which
    statements are one fact is `insight_reconciler`'s, after all batches."""
    items = list(findings_by_attribute.items())
    if not items:
        return [], []

    # Flatten to independent (attribute_ref, batch) units in document-variable order.
    #
    # Program-scoped findings are excluded, not merely absent: an insight is a statement
    # about one document variable, and these findings belong to no variable. Letting them
    # through would produce an insight whose `attribute_ref` names no attribute, which
    # the result assembly refuses outright - so the filter turns a runtime failure into a
    # stated rule. Their route downstream is the development landscape, which groups by
    # program name and does not read this key.
    batch_tasks: list[tuple[str, list[Finding]]] = [
        (attribute_ref, batch)
        for attribute_ref, findings in items
        if attribute_ref != PROGRAM_SCOPE_KEY
        for batch in _finding_batches(
            [finding for finding in findings if finding.evidence_role == "evidence"]
        )
    ]
    if not batch_tasks:
        return [], []

    def one(task: tuple[str, list[Finding]]) -> list[Insight]:
        attribute_ref, batch = task
        return extract_insights(
            batch,
            openai_client,
            indication=indication,
            intervention_class=intervention_class,
            attribute_ref=attribute_ref,
            attribute_description=attribute_descriptions.get(attribute_ref, ""),
            lineage=lineage,
        )

    results = _parallel_map(
        batch_tasks, one, workers=MAX_WORKERS, stage="insights", progress=progress
    )
    insights = [insight for batch_insights in results for insight in batch_insights]
    return reconcile_duplicate_insights(insights, openai_client)


def _interleave_by_evidence_class(findings: list[Finding]) -> list[Finding]:
    """Round-robin findings across the evidence classes present, in arrival order.

    Retrieval returns lane by lane, so a batch built straight from arrival order holds
    one class: a prompt of twenty abstracts, then a prompt of twenty trial records.
    Nothing is lost that way - `budgeted_batches` keeps every finding - but no prompt
    ever holds a registry record beside the literature it should be read against, and
    a comparison the model cannot see in one prompt is one it cannot make.

    Round-robin rather than a share: a share would have to decide how much each class
    deserves, and that is a judgement no batcher can make. Alternating spends the same
    budget on the same findings and only changes which ones arrive together, so a class
    returning two findings is not thereby ranked below one returning twenty.

    Order within a class is preserved, so each lane's own relevance ranking survives.
    """
    by_class: dict[str, list[Finding]] = {}
    for finding in findings:
        by_class.setdefault(lane_class(finding.source), []).append(finding)
    if len(by_class) < 2:
        return list(findings)
    queues = list(by_class.values())
    interleaved: list[Finding] = []
    while queues:
        for queue in list(queues):
            interleaved.append(queue.pop(0))
            if not queue:
                queues.remove(queue)
    return interleaved


def _finding_batches(findings: list[Finding]) -> list[list[Finding]]:
    """Partition findings without dropping any source or overfilling one prompt."""
    def rendered_size(finding: Finding) -> int:
        return (
            len(finding.title or "")
            + len(finding.excerpt or "")
            + len(finding.url or "")
            + sum(len(query) for query in finding.queries)
        )

    return budgeted_batches(
        _interleave_by_evidence_class(findings),
        max_items=FINDINGS_PER_REQUEST,
        max_chars=FINDINGS_CHARS_PER_REQUEST,
        size_of=rendered_size,
    )


def _search_all(
    tasks: list[SearchRequest],
    runtime: SearchRuntime,
    *,
    published_since: str = "",
    progress: ProgressFn | None = None,
) -> tuple[dict[str, list[Finding]], int, list[SearchTrace]]:
    """Run Searcher's controller and merge normalized findings per Scout unit.

    This is the one place retrieved evidence enters the run, so a requested
    window is applied here rather than at display: every insight, precedent, and
    benchmark statistic downstream must describe the cohort the user asked for,
    not a filtered view of a wider one.

    A source that supplied no publication date leaves the finding admitted. Web
    pages rarely carry one, and treating an absent date as an old date would
    silently discard current evidence. A date stated only to the month or year is
    before the window only if all of it is (`Finding.published_before`).

    One record retrieved by several requests of one field is one finding, merged by
    record identity with every lane and path kept (`dedupe_findings`). Each field gets
    its own copies, so merging one field's retrievals never rewrites another's.
    """
    if not tasks:
        return {}, 0, []
    window_start = date.fromisoformat(published_since) if published_since else None
    outcomes = run_requests(
        tasks,
        runtime=runtime,
        max_tokens=SEARCH_MAX_TOKENS,
        progress=_stage_counts(progress, "search"),
    )

    retrieved: dict[str, list[Finding]] = {}
    excluded_by_outcome: dict[int, list[str]] = {}
    total_findings = 0
    for outcome in outcomes:
        excluded = excluded_by_outcome.setdefault(id(outcome), [])
        output = retrieved.setdefault(outcome.request.scope_ref, [])
        for finding in outcome.findings:
            if window_start is not None and finding.published_before(window_start):
                excluded.append(finding.url)
                continue
            total_findings += 1
            output.append(copy.copy(finding))

    def trace_for(outcome) -> SearchTrace:
        task = outcome.request
        return SearchTrace(
            attribute_ref=task.scope_ref,
            lane=task.source,
            query=task.query,
            connector=task.connector,
            operation=task.operation,
            request_options=dict(task.options),
            tracks=list(task.tracks),
            doc_block_ids=list(task.document_refs),
            target_ids=list(task.target_refs),
            intent_ids=list(task.intent_ids),
            input_queries=list(task.input_queries),
            applicability=task.applicability,
            applicability_reason=task.applicability_reason,
            status=outcome.status,
            error=outcome.error,
            error_code=outcome.error_code,
            provider_query=outcome.provider_query,
            warnings=list(outcome.warnings),
            # The retrieval record stays complete: `source_urls` is what the
            # source returned, and the exclusions name which of those the window
            # held out.
            finding_count=len(outcome.findings),
            source_urls=[finding.url for finding in outcome.findings],
            excluded_before_window=list(
                dict.fromkeys(excluded_by_outcome.get(id(outcome), []))
            ),
        )

    search_plan = [trace_for(outcome) for outcome in outcomes]
    return (
        {
            attribute: dedupe_findings(findings)
            for attribute, findings in retrieved.items()
            if findings
        },
        total_findings,
        search_plan,
    )


def _classify_drift_all(
    attribute_contexts: dict[str, str],
    insights: list[Insight],
    openai_client: LLMClientProtocol,
    *,
    indication: str,
    intervention_class: str,
    framing: str = "",
    attribute_images: dict[str, list[dict[str, str]]] | None = None,
    progress: ProgressFn | None = None,
) -> list[Match]:
    """Classify each insight against its own variable's binding, one request each."""
    if not insights:
        return []
    grouped = _group_insights_by_attribute(insights, set(attribute_contexts))
    tasks = [insight for variable_insights in grouped.values() for insight in variable_insights]

    def one(insight: Insight) -> Match:
        attribute_ref = insight.attribute_ref or ""
        return classify_drift(
            attribute_contexts.get(attribute_ref, ""),
            insight,
            openai_client,
            indication=indication,
            intervention_class=intervention_class,
            framing=framing,
            images=(attribute_images or {}).get(attribute_ref) or None,
        )

    return _parallel_map(tasks, one, workers=MAX_WORKERS, stage="classify", progress=progress)


def _assess_evidence_all_variables(
    attributes: list[Attribute],
    attribute_contexts: dict[str, str],
    insights: list[Insight],
    openai_client: LLMClientProtocol,
    *,
    indication: str,
    intervention_class: str,
    framing: str = "",
    attribute_images: dict[str, list[dict[str, str]]] | None = None,
    progress: ProgressFn | None = None,
) -> list[EvidenceAssessment]:
    """Assess evidence per attribute with bounded concurrency."""
    if not attributes:
        return []
    insights_by_attribute = _group_insights_by_attribute(
        insights, {attribute.name for attribute in attributes}
    )

    def one(attribute: Attribute) -> EvidenceAssessment:
        return assess_evidence(
            attribute,
            attribute_contexts.get(attribute.name, ""),
            insights_by_attribute.get(attribute.name, []),
            openai_client,
            indication=indication,
            intervention_class=intervention_class,
            framing=framing,
            images=(attribute_images or {}).get(attribute.name) or None,
        )

    return _parallel_map(
        attributes, one, workers=MAX_WORKERS, stage="evidence", progress=progress
    )


def _score_conformity_all_variables(
    attributes: list[Attribute],
    quantitative_targets: list[QuantitativeTarget],
    insights: list[Insight],
    openai_client: LLMClientProtocol,
    *,
    indication: str,
    intervention_class: str,
    progress: ProgressFn | None = None,
) -> list[ConformityScore]:
    """Score quantitative conformity through one bounded global work queue.

    Self-gating: returns ledgers only for variables with an exact-quoted numeric
    target. A valid target with no admitted comparators remains an explicit
    insufficient cohort rather than disappearing."""
    if not attributes:
        return []
    insights_by_attribute = _group_insights_by_attribute(
        insights, {attribute.name for attribute in attributes}
    )

    return score_conformity_all(
        attributes,
        quantitative_targets,
        insights_by_attribute,
        openai_client,
        indication=indication,
        intervention_class=intervention_class,
        progress_callback=_stage_counts(progress, "conformity"),
    )


def _classify_precedent_all_variables(
    attributes: list[Attribute],
    attribute_contexts: dict[str, str],
    insights: list[Insight],
    openai_client: LLMClientProtocol,
    *,
    indication: str,
    intervention_class: str,
    framing: str = "",
    attribute_images: dict[str, list[dict[str, str]]] | None = None,
    progress: ProgressFn | None = None,
) -> list[PrecedentSignal]:
    """Classify precedent per attribute with bounded concurrency.

    One signal per searchable attribute: a variable no insight reached is recorded
    ``no_evidence`` without a call, never dropped."""
    if not attributes:
        return []
    insights_by_attribute = _group_insights_by_attribute(
        insights, {attribute.name for attribute in attributes}
    )

    def one(attribute: Attribute) -> PrecedentSignal:
        return classify_precedent(
            attribute,
            attribute_contexts.get(attribute.name, ""),
            insights_by_attribute.get(attribute.name, []),
            openai_client,
            indication=indication,
            intervention_class=intervention_class,
            framing=framing,
            images=(attribute_images or {}).get(attribute.name) or None,
        )

    return _parallel_map(
        attributes, one, workers=MAX_WORKERS, stage="precedent", progress=progress
    )


def _group_insights_by_attribute(
    insights: list[Insight],
    known_attributes: set[str],
) -> dict[str, list[Insight]]:
    """Build the one field-isolation boundary shared by every reasoning axis."""
    grouped: dict[str, list[Insight]] = {}
    for insight in insights:
        attribute_ref = insight.attribute_ref
        if not attribute_ref or attribute_ref not in known_attributes:
            raise ValueError(
                f"insight {insight.id!r} references unknown field {attribute_ref!r}"
            )
        grouped.setdefault(attribute_ref, []).append(insight)
    return grouped


def _empty_result(
    *,
    context_validation: DocumentContextValidation,
    retrieval_scope: RetrievalScopeLedger,
    queries: int = 0,
    blocks: list[ContentBlock] | None = None,
    variables: list[Attribute] | None = None,
    quantitative_ledger: QuantitativeLedger | None = None,
    search_plan: list[SearchTrace] | None = None,
    published_since: str = "",
    reconciliations: list[IdentityReconciliation] | None = None,
    not_searched_fields: list[str] | None = None,
) -> ScoutResult:
    """A final result for a run whose retrieval returned nothing to read.

    Every searched variable still gets its grounding and precedent record, as
    ``no_evidence``: the subject is kept, so "nothing was retrieved for it" reads as
    that rather than as a variable the run never considered. A variable the reviewer
    left out is ``not_searched``.
    """
    not_searched = set(not_searched_fields or [])
    searchable = _searchable(variables or [])
    assessments = [
        _not_searched_assessment(attribute) if attribute.name in not_searched
        else no_evidence_assessment(attribute)
        for attribute in searchable
    ]
    return validate_result_contract(ScoutResult(
        matches=[],
        assessments=assessments,
        stats=FunnelStats(
            queries=queries,
            findings=0,
            unique_findings=0,
            insights=0,
            matches=0,
            assessments=len(assessments),
        ),
        variables=variables or [],
        quantitative_ledger=quantitative_ledger or QuantitativeLedger(),
        conformity=empty_conformity_scores(
            (
                _calibrated_targets(quantitative_ledger, not_searched)
                if quantitative_ledger
                else []
            )
        ),
        precedents=[
            _not_searched_precedent(attribute) if attribute.name in not_searched
            else no_evidence_precedent(attribute)
            for attribute in searchable
        ],
        search_plan=search_plan or [],
        context_validation=context_validation,
        blocks=blocks or [],
        published_since=published_since,
        retrieval_scope=retrieval_scope,
        reconciliations=reconciliations or [],
        not_searched_fields=list(not_searched_fields or []),
    ))


def _calibrated_targets(
    ledger: QuantitativeLedger,
    not_searched: set[str],
) -> list[QuantitativeTarget]:
    """Approved claims that drive at least one searched field.

    A target whose fields were all left out at review stays in the ledger as reviewed
    and is not calibrated: no insight of a searched field could measure it.
    """
    return [
        target
        for target in ledger.targets
        if target.review_status == "approved"
        and any(ref not in not_searched for ref in target.analysis_attribute_refs)
    ]


def _stamp(
    insights: list[Insight],
    *,
    org: str,
    source_type: str,
    intervention_class: str,
    indication: str,
) -> None:
    for insight in insights:
        insight.org = org
        insight.source_type = source_type
        insight.intervention_class = intervention_class
        insight.indication = indication
