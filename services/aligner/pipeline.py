from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import threading

from services.chunker import (
    ContentBlock,
    find_config as find_chunker_config,
    run_pipeline as chunker_run_pipeline,
)

from .models import (
    AlignmentConfig,
    AlignmentDocument,
    AlignmentResult,
    LLMClientProtocol,
)
from .contract import validate_result_contract
from .stages.extractor import extract_units
from .stages.linker import align_units

DEFAULT_MAX_OUTPUT_TOKENS = 12000


def run_pipeline(
    reference_file_path: str,
    comparison_file_path: str,
    *,
    reference_source_type: str,
    comparison_source_type: str,
    org: str,
    intervention_class: str,
    indication: str,
    config: AlignmentConfig,
    llm_client: LLMClientProtocol,
    reference_doc_id: str | None = None,
    comparison_doc_id: str | None = None,
    max_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
    progress_callback=None,
) -> AlignmentResult:
    reference_config = find_chunker_config(org, reference_source_type, intervention_class)
    comparison_config = find_chunker_config(org, comparison_source_type, intervention_class)
    reference_id = reference_doc_id or Path(reference_file_path).stem
    comparison_id = comparison_doc_id or Path(comparison_file_path).stem
    if reference_id == comparison_id:
        raise ValueError("Reference and comparison documents must have distinct filenames")

    parse_jobs = [
        (
            "reference",
            reference_file_path,
            reference_id,
            reference_source_type,
            reference_config,
        ),
        (
            "comparison",
            comparison_file_path,
            comparison_id,
            comparison_source_type,
            comparison_config,
        ),
    ]
    if progress_callback:
        progress_callback("parse", completed=0, total=2)
    parse_lock = threading.Lock()
    parsed_count = {"value": 0}

    def parse(job):
        role, file_path, doc_id, source_type, chunker_config = job
        blocks = chunker_run_pipeline(
            file_path,
            doc_id=doc_id,
            config=chunker_config,
            llm_client=llm_client,
            max_tokens=max_tokens,
            indication=indication,
        )
        if progress_callback:
            with parse_lock:
                parsed_count["value"] += 1
                progress_callback("parse", completed=parsed_count["value"], total=2)
        return role, blocks

    parsed: dict[str, list[ContentBlock]] = {}
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(parse, job) for job in parse_jobs]
        for future in as_completed(futures):
            role, blocks = future.result()
            parsed[role] = blocks

    if progress_callback:
        progress_callback("extract", completed=0, total=2)
    extract_jobs = [
        ("reference", parsed["reference"], reference_source_type),
        ("comparison", parsed["comparison"], comparison_source_type),
    ]
    extract_lock = threading.Lock()
    extracted_count = {"value": 0}
    extraction_workers_per_document = max(1, config.max_parallel_calls // 2)

    def extract(job):
        role, blocks, source_type = job
        units = extract_units(
            blocks,
            document_role=role,
            source_type=source_type,
            config=config,
            llm_client=llm_client,
            max_tokens=max_tokens,
            max_workers=extraction_workers_per_document,
        )
        if progress_callback:
            with extract_lock:
                extracted_count["value"] += 1
                progress_callback("extract", completed=extracted_count["value"], total=2)
        return role, units

    units_by_role = {}
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(extract, job) for job in extract_jobs]
        for future in as_completed(futures):
            role, units = future.result()
            units_by_role[role] = units

    if progress_callback:
        progress_callback("align")
    links, stats = align_units(
        units_by_role["reference"],
        units_by_role["comparison"],
        config=config,
        llm_client=llm_client,
        max_tokens=max_tokens,
    )
    all_units = [*units_by_role["reference"], *units_by_role["comparison"]]
    all_blocks = [*parsed["reference"], *parsed["comparison"]]
    result = AlignmentResult(
        reference_document=AlignmentDocument(
            role="reference",
            doc_id=reference_id,
            source_type=reference_source_type,
            display_name=reference_config.display_name,
        ),
        comparison_document=AlignmentDocument(
            role="comparison",
            doc_id=comparison_id,
            source_type=comparison_source_type,
            display_name=comparison_config.display_name,
        ),
        units=all_units,
        links=links,
        stats=stats,
        org=org,
        intervention_class=intervention_class,
        indication=indication,
        unit_types=config.unit_types,
        relations=config.relations,
        blocks=all_blocks,
    )
    result = validate_result_contract(result, config)
    return result
