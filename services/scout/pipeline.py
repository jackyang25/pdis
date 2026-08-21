"""Stateless scout pipeline.

Orchestrates: chunker (parse only) -> canonical target binding -> per-unit query
generation (LLM) -> lane-native retrieval routing -> searcher -> per-unit insight
extraction (LLM) -> four independent reasoning layers. Reuses chunker and
searcher through their public contracts only.
"""

from __future__ import annotations

import threading
from datetime import date
from pathlib import Path
from typing import Callable, TypeVar

from services.chunker import ContentBlock, run_pipeline as chunker_run
from services.searcher import (
    Finding,
    lane_class,
    SearchRequest,
    SearchRuntime,
    merge_findings,
    plan_requests,
    run_requests,
)

from .context import (
    document_block_ids,
    render_canonical_binding,
    render_document_context,
)
from .contract import validate_result_contract
from shared.batching import budgeted_batches, fixed_batches, map_ordered
from shared.vocabulary import search_term
from .models import (
    PROGRAM_SCOPE_KEY,
    RetrievalScopeLedger,
    Attribute,
    ConformityScore,
    DocumentContextValidation,
    EvidenceAssessment,
    FunnelStats,
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
    build_burden_indicators,
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
from .stages.drift_classifier import INSIGHTS_PER_REQUEST, classify_drift
from .stages.evidence_assessor import assess_evidence
from .stages.evidence_reviewer import prefill_evidence_review
from .stages.insight_extractor import extract_insights, merge_duplicate_insights
from .stages.insight_reconciler import reconcile_duplicate_insights
from .stages.precedent_classifier import classify_precedent
from .stages.projection_classifier import classify_projection_relationships
from .stages.announcement_reader import read_announcements
from .stages.scope_resolver import resolve_retrieval_scope
from .stages.query_extractor import extract_queries_for_variable
from .stages.intent_builder import build_program_intents, build_retrieval_intents
from .stages.target_resolver import resolve_document_targets
from .stages.target_reviewer import prefill_target_review
from .stages.unit_extractor import extract_units

FINDINGS_PER_REQUEST = 40
FINDINGS_CHARS_PER_REQUEST = 240_000
SEARCH_MAX_TOKENS = 8000
SEARCH_MAX_USES = 10

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

    if progress_callback:
        progress_callback("context")
    context_validation = validate_document_context(
        doc_text,
        openai_client,
        indication=indication,
        images=[
            {"block_id": block.id, "data_url": block.image.data_url()}
            for block in blocks
            if block.image
        ]
        or None,
    )
    if context_validation.status == "mismatch":
        raise ValueError(mismatch_message(context_validation))

    attributes = _resolve_units(
        config, doc_text, blocks, openai_client, indication=indication
    )
    if not attributes:
        return validate_result_contract(ScoutResult(
            matches=[],
            assessments=[],
            stats=FunnelStats(
                queries=0,
                findings=0,
                unique_findings=0,
                insights=0,
                matches=0,
                assessments=0,
            ),
            context_validation=context_validation,
            blocks=blocks,
            published_since=published_since,
        ))

    # Provider-specific work ends here. Fixed definitions are resolved in
    # bounded output batches that share the same document and complete field
    # catalog; dynamically extracted units arrive already bound. Every later
    # stage receives the same canonical Attribute contract.
    attributes = _resolve_targets_all(
        attributes,
        doc_text,
        blocks,
        openai_client,
        progress=progress_callback,
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
        return _empty_result(
            blocks=blocks,
            variables=attributes,
            quantitative_ledger=QuantitativeLedger(
                status="not_applicable",
                reason=(
                    "Numeric interpretation did not run because document claim "
                    "resolution stopped before retrieval: "
                    f"{len(unresolved_attributes)} field decision(s) remained unresolved "
                    "after one bounded retry."
                ),
            ),
            context_validation=context_validation,
            published_since=published_since,
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
    attributes, quantitative_ledger = reconcile_quantitative_document_ledger(
        attributes,
        quantitative_ledger,
        quantitative_mapping_client,
    )
    if progress_callback:
        progress_callback("target_review")
    attributes, quantitative_ledger = prefill_target_review(
        attributes,
        quantitative_ledger,
        blocks,
        openai_client,
    )
    return validate_result_contract(ScoutResult(
        matches=[],
        assessments=[],
        stats=FunnelStats(
            queries=0,
            findings=0,
            unique_findings=0,
            insights=0,
            matches=0,
            assessments=0,
        ),
        context_validation=context_validation,
        quantitative_ledger=quantitative_ledger,
        variables=attributes,
        blocks=blocks,
        phase="target_review",
        # Declared before retrieval and carried through the review round-trip,
        # so the continuation searches the window the user actually chose.
        published_since=published_since,
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
    """Continue from one explicitly reviewed, portable target draft."""
    validate_result_contract(prepared)
    # Nothing here re-stamps a block — the draft carries its own, already stamped with
    # the stored tag — so the tag is only ever text from this point, normalised once for
    # the same reason as in `run_pipeline`.
    indication = search_term(indication)
    intervention_class = search_term(intervention_class)
    if prepared.phase != "target_review":
        raise ValueError("Scout continuation requires a target-review draft")
    blocks = prepared.blocks
    context_validation = prepared.context_validation
    attributes, quantitative_ledger = finalize_quantitative_document_review(
        prepared.variables,
        prepared.quantitative_ledger,
    )
    active_quantitative_targets = _active_quantitative_targets(quantitative_ledger)
    # Numeric interpretation is load-bearing only for quantitative calibration.
    # An unresolved statement remains excluded from target-specific queries and
    # statistics, but it must not discard the already verified document-claim
    # ledger or prevent the independent qualitative evidence workflow.
    searchable_attributes = [
        attribute
        for attribute in attributes
        if attribute.document_target and attribute.document_spans
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

    # One statement of what this run is about, recorded with where each value came from.
    # The header supplies the condition and class; the document supplies the geography,
    # read from whichever attribute declares `supplies_scope` for it. A dimension nobody
    # supplies is recorded unset rather than omitted, so it stays distinguishable from a
    # reader who deliberately widened the search.
    #
    # Resolved here rather than beside retrieval, because two layers read it and both are
    # downstream of this point: query generation, which needs the geography to write
    # queries about the right places, and the adapters, which need it to filter. Resolved
    # after retrieval it would reach only the second, which is what it used to do.
    retrieval_scope = resolve_retrieval_scope(
        prepared.variables,
        openai_client,
        condition=indication,
        intervention_class=intervention_class,
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
        return _empty_result(
            blocks=blocks,
            variables=attributes,
            quantitative_ledger=quantitative_ledger,
            context_validation=context_validation,
            published_since=prepared.published_since,
        )

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
        return _empty_result(
            queries=len(flat),
            blocks=blocks,
            variables=attributes,
            quantitative_ledger=quantitative_ledger,
            search_plan=search_plan,
            context_validation=context_validation,
            published_since=prepared.published_since,
        )

    # Adapters own source-specific parsing. These views consume only normalized
    # records and therefore add no new model judgment or provider branch here.
    # Program-scoped findings are prose, so the record the landscape groups by has to be
    # read out of them. Before the landscape is built, and only for findings that carry
    # no record yet.
    announcements = read_announcements(
        findings_by_attribute.get(PROGRAM_SCOPE_KEY, []), openai_client
    )
    development_landscape = build_development_landscape(findings_by_attribute)
    safety_observations = build_safety_observations(findings_by_attribute)
    burden_indicators = build_burden_indicators(findings_by_attribute)
    development_landscape, safety_observations = classify_projection_relationships(
        searchable_attributes,
        development_landscape,
        safety_observations,
        openai_client,
        indication=indication,
        intervention_class=intervention_class,
    )

    query_tracks_by_attribute: dict[str, dict[str, list[str]]] = {}
    query_targets_by_attribute: dict[str, dict[str, list[str]]] = {}
    for task in search_tasks:
        if task.tracks:
            track_map = query_tracks_by_attribute.setdefault(task.scope_ref, {})
            track_map[task.query] = list(
                dict.fromkeys([*track_map.get(task.query, []), *task.tracks])
            )
        if task.target_refs:
            target_map = query_targets_by_attribute.setdefault(task.scope_ref, {})
            target_map[task.query] = list(
                dict.fromkeys(
                    [*target_map.get(task.query, []), *task.target_refs]
                )
            )

    if progress_callback:
        progress_callback("insights")
    insights = _extract_insights_all_variables(
        findings_by_attribute,
        attribute_descriptions,
        query_tracks_by_attribute,
        query_targets_by_attribute,
        openai_client,
        indication=indication,
        intervention_class=intervention_class,
        progress=progress_callback,
    )

    _stamp(
        insights,
        org=org,
        source_type=source_type,
        intervention_class=intervention_class,
        indication=indication,
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

    stats = FunnelStats(
        queries=len(flat),
        findings=total_findings,
        unique_findings=len({
            finding.url
            for findings in findings_by_attribute.values()
            for finding in findings
        }),
        insights=len(insights),
        matches=len(matches),
        assessments=len(assessments),
        announcements_read=announcements.read,
        announcements_named=announcements.named,
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
        burden_indicators=burden_indicators,
        context_validation=context_validation,
        quantitative_ledger=quantitative_ledger,
        variables=attributes,
        blocks=blocks,
        phase="evidence_review" if has_evidence_review else "final",
        published_since=prepared.published_since,
    ))


def _resolve_units(
    config: ScoutTypeConfig,
    doc_text: str,
    blocks: list[ContentBlock],
    openai_client: LLMClientProtocol,
    *,
    indication: str,
) -> list[Attribute]:
    """Get definitions from the configured provider.

    ``vocabulary`` reads fixed definitions; ``extract`` returns dynamically
    defined units already bound to their document targets. The next stage binds
    fixed definitions so provider-specific semantics end before retrieval.
    """
    if config.unit_provider == "extract":
        return extract_units(
            doc_text,
            intervention_class=config.intervention_term,
            source_type=config.source_type,
            indication=indication,
            llm_client=openai_client,
            images_by_block_id={
                block.id: block.image.data_url()
                for block in blocks
                if block.image
            },
        )
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
    `progress(stage, completed, total)` as each task FINISHES.

    The completion counter is lock-guarded because tasks finish on worker
    threads; the streaming queue the callback writes to is itself thread-safe.
    """
    total = len(items)
    if total == 0:
        return []
    if progress:
        progress(stage, completed=0, total=total)

    lock = threading.Lock()
    state = {"done": 0}

    def run_one(item: _T) -> _R:
        result = fn(item)
        if progress:
            with lock:
                state["done"] += 1
                progress(stage, completed=state["done"], total=total)
        return result

    return map_ordered(items, run_one, workers=workers)


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
            queries_per_variable=config.queries_per_variable,
            document_context=query_contexts.get(attribute.name, ""),
        )

    results = _parallel_map(
        attributes, one, workers=MAX_WORKERS, stage="queries", progress=progress
    )
    return {name: queries for name, queries in results if queries}


def _resolve_targets_all(
    attributes: list[Attribute],
    document_context: str,
    blocks: list[ContentBlock],
    openai_client: LLMClientProtocol,
    *,
    progress: ProgressFn | None = None,
) -> list[Attribute]:
    """Build one canonical claim ledger, then expose its Attribute projection."""
    resolved = resolve_document_targets(
        attributes,
        document_context,
        openai_client,
        images=[
            {"block_id": block.id, "data_url": block.image.data_url()}
            for block in blocks
            if block.image
        ]
        or None,
        progress_callback=(
            (lambda **counts: progress("targets", **counts)) if progress else None
        ),
    )
    return resolved


def _images_for_contexts(
    contexts: dict[str, str],
    blocks: list[ContentBlock],
) -> dict[str, list[dict[str, str]]]:
    """Attach visuals by the exact block IDs present in each bounded context."""
    output: dict[str, list[dict[str, str]]] = {}
    for attribute_ref, context in contexts.items():
        context_ids = document_block_ids(context)
        output[attribute_ref] = [
            {
                "block_id": block.id,
                "data_url": block.image.data_url(),
            }
            for block in blocks
            if block.image and block.id in context_ids
        ]
    return output


def _extract_insights_all_variables(
    findings_by_attribute: dict[str, list[Finding]],
    attribute_descriptions: dict[str, str],
    query_tracks_by_attribute: dict[str, dict[str, list[str]]],
    query_targets_by_attribute: dict[str, dict[str, list[str]]],
    openai_client: LLMClientProtocol,
    *,
    indication: str,
    intervention_class: str,
    progress: ProgressFn | None = None,
) -> list[Insight]:
    """Run insight extraction concurrently across all (variable, finding-batch)
    units.

    Every evidence-role finding is retained; reference-role records are excluded
    because they carry catalog metadata rather than evidence. Batches are bounded
    by both item count and rendered character size so one unusually large source
    cannot crowd the model context.
    Each task remains single-variable and results are deterministically merged,
    preventing duplicate insights created at batch boundaries."""
    items = list(findings_by_attribute.items())
    if not items:
        return []

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
        return []

    def one(task: tuple[str, list[Finding]]) -> list[Insight]:
        attribute_ref, batch = task
        return extract_insights(
            batch,
            openai_client,
            indication=indication,
            intervention_class=intervention_class,
            attribute_ref=attribute_ref,
            attribute_description=attribute_descriptions.get(attribute_ref, ""),
            query_tracks=query_tracks_by_attribute.get(attribute_ref, {}),
            query_targets=query_targets_by_attribute.get(attribute_ref, {}),
        )

    results = _parallel_map(
        batch_tasks, one, workers=MAX_WORKERS, stage="insights", progress=progress
    )

    insights: list[Insight] = []
    for batch_insights in results:
        insights.extend(batch_insights)
    # Extraction creates objects; identity is decided after it. Code merges only
    # statements that are literally the same, then one bounded model layer groups
    # the paraphrases no single extraction request could see.
    return reconcile_duplicate_insights(
        merge_duplicate_insights(insights),
        openai_client,
    )


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
    silently discard current evidence.
    """
    if not tasks:
        return {}, 0, []
    window_start = date.fromisoformat(published_since) if published_since else None
    outcomes = run_requests(
        tasks,
        runtime=runtime,
        max_tokens=SEARCH_MAX_TOKENS,
        max_uses=SEARCH_MAX_USES,
        progress=(
            lambda completed, total: progress(
                "search", completed=completed, total=total
            )
        )
        if progress
        else None,
    )

    def before_window(finding: Finding) -> bool:
        if window_start is None or finding.published_at is None:
            return False
        return finding.published_at.date() < window_start

    findings_by_attribute: dict[str, list[Finding]] = {}
    by_attribute_url: dict[str, dict[str, Finding]] = {}
    excluded_by_outcome: dict[int, list[str]] = {}
    total_findings = 0
    for outcome in outcomes:
        task = outcome.request
        excluded = excluded_by_outcome.setdefault(id(outcome), [])
        output = findings_by_attribute.setdefault(task.scope_ref, [])
        by_url = by_attribute_url.setdefault(task.scope_ref, {})
        for finding in outcome.findings:
            if before_window(finding):
                excluded.append(finding.url)
                continue
            total_findings += 1
            if finding.url in by_url:
                merge_findings(by_url[finding.url], finding)
                continue
            by_url[finding.url] = finding
            output.append(finding)

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
        {attribute: findings for attribute, findings in findings_by_attribute.items() if findings},
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
    """Classify drift in single-variable batches against that variable's context."""
    if not insights:
        return []

    grouped = _group_insights_by_attribute(insights, set(attribute_contexts))
    tasks = [
        (attribute_ref, attribute_contexts.get(attribute_ref, ""), batch)
        for attribute_ref, variable_insights in grouped.items()
        for batch in fixed_batches(variable_insights, INSIGHTS_PER_REQUEST)
    ]

    def one(task: tuple[str, str, list[Insight]]) -> list[Match]:
        attribute_ref, context, batch = task
        return classify_drift(
            [context],
            batch,
            openai_client,
            indication=indication,
            intervention_class=intervention_class,
            framing=framing,
            images=(attribute_images or {}).get(attribute_ref) or None,
        )

    results = _parallel_map(
        tasks, one, workers=MAX_WORKERS, stage="classify", progress=progress
    )
    matches: list[Match] = []
    for batch_matches in results:
        matches.extend(batch_matches)
    return matches


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
        progress_callback=(
            (
                lambda completed, total: progress(
                    "conformity", completed=completed, total=total
                )
            )
            if progress
            else None
        ),
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

    Self-gating: returns a signal only for variables with external evidence
    (classify_precedent returns None otherwise)."""
    if not attributes:
        return []
    insights_by_attribute = _group_insights_by_attribute(
        insights, {attribute.name for attribute in attributes}
    )

    def one(attribute: Attribute) -> PrecedentSignal | None:
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

    results = _parallel_map(
        attributes, one, workers=MAX_WORKERS, stage="precedent", progress=progress
    )
    return [signal for signal in results if signal is not None]


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
    queries: int = 0,
    findings: int = 0,
    unique_findings: int = 0,
    insights: int = 0,
    blocks: list[ContentBlock] | None = None,
    variables: list[Attribute] | None = None,
    quantitative_ledger: QuantitativeLedger | None = None,
    search_plan: list[SearchTrace] | None = None,
    published_since: str = "",
) -> ScoutResult:
    return validate_result_contract(ScoutResult(
        matches=[],
        assessments=[],
        stats=FunnelStats(
            queries=queries,
            findings=findings,
            unique_findings=unique_findings,
            insights=insights,
            matches=0,
            assessments=0,
        ),
        variables=variables or [],
        quantitative_ledger=quantitative_ledger or QuantitativeLedger(),
        conformity=empty_conformity_scores(
            (
                _active_quantitative_targets(quantitative_ledger)
                if quantitative_ledger
                else []
            )
        ),
        search_plan=search_plan or [],
        context_validation=context_validation,
        blocks=blocks or [],
        published_since=published_since,
    ))


def _active_quantitative_targets(
    ledger: QuantitativeLedger,
) -> list[QuantitativeTarget]:
    """Project approved claims from the immutable review audit ledger."""
    return [
        target for target in ledger.targets if target.review_status == "approved"
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
