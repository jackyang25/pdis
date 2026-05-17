"""CLI: grade a chunker package against a PD Reviewer rubric.

Reads a chunker package (documents.csv + content_blocks.csv produced by
`python -m chunker.cli`) and grades every successfully-mapped document.
Outputs review CSVs + manifest.

The header (org, source_type, intervention_class) is read from the chunker
package contents (every row carries the header columns). Therapeutic area
is an optional CLI flag.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import os
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.chunker import ContentBlock  # noqa: E402
from services.evidence import FileClaimsStore  # noqa: E402
from llm_client import create_llm_client, default_model_for_provider  # noqa: E402

from .models import ReviewConfig, ReviewResult, SectionGrade, find_config  # noqa: E402
from .pipeline import DEFAULT_MAX_OUTPUT_TOKENS, GRADE_TO_SCORE, review_blocks_batch  # noqa: E402


logger = logging.getLogger(__name__)


HEADER_COLUMNS = ["org", "source_type", "intervention_class", "therapeutic_area"]


DOCUMENT_SCORE_COLUMNS = [
    "doc_key",
    *HEADER_COLUMNS,
    "file_name",
    "overall_grade",
    "weighted_score",
    "sections_total",
    "sections_present",
    "sections_missing",
    "top_issues_json",
    "review_status",
    "review_error",
]

SECTION_GRADE_COLUMNS = [
    "doc_key",
    *HEADER_COLUMNS,
    "section_name",
    "weight",
    "grade",
    "score",
    "is_present",
    "missing_variables_json",
    "issues_json",
    "recommendation",
    "variable_grades_count",
]

VARIABLE_GRADE_COLUMNS = [
    "doc_key",
    *HEADER_COLUMNS,
    "section_name",
    "variable_name",
    "grade",
    "score",
    "issues_json",
    "recommendation",
    "block_ids_json",
]


@dataclass
class _DocumentRecord:
    """Per-document inputs assembled from the chunker package."""

    doc_key: str
    header: dict[str, Any]
    file_name: str
    blocks: list[ContentBlock]


def export_review_package(
    input_dir: str,
    output_dir: str,
    *,
    provider: str = "openai",
    model: str | None = None,
    api_key: str | None = None,
    max_workers: int = 4,
    max_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
    therapeutic_area: str | None = None,
    claims_dir: str | None = None,
) -> None:
    """Run PD Reviewer over a chunker package and write review tables."""
    input_path = Path(input_dir).expanduser().resolve()
    output_path = Path(output_dir).expanduser().resolve()
    if not input_path.is_dir():
        raise ValueError(f"input_dir must be an existing directory: {input_path}")

    documents_csv = input_path / "documents.csv"
    blocks_csv = input_path / "content_blocks.csv"
    if not documents_csv.exists() or not blocks_csv.exists():
        raise ValueError(
            "input_dir must contain documents.csv and content_blocks.csv "
            "(a parsed + mapped chunker package)"
        )

    api_key = api_key or os.getenv(_api_key_env_var(provider))
    if not api_key:
        raise ValueError(
            f"api key is required. Set {_api_key_env_var(provider)} or pass --api-key."
        )

    document_rows = _read_csv(documents_csv)
    block_rows = _read_csv(blocks_csv)

    header = _resolve_header_from_package(document_rows, therapeutic_area)
    config = find_config(header["org"], header["source_type"], header["intervention_class"])
    if config is None:
        org, src, iv = header["org"], header["source_type"], header["intervention_class"]
        raise ValueError(
            f"No PD Reviewer rubric for ({org}, {src}, {iv}). "
            f"Expected: pd_reviewer/configs/{org}_{src}_{iv}.yaml"
        )

    llm_client = create_llm_client(provider, api_key, model=model)

    records = _build_document_records(document_rows, block_rows, header)
    if not records:
        raise ValueError("No reviewable documents found (need parse_status=ok and mapping_status=ok)")

    claims_store = FileClaimsStore(claims_dir) if claims_dir else None
    if claims_store is not None:
        logger.info("Loaded %d claims from %s", len(claims_store), claims_dir)

    output_path.mkdir(parents=True, exist_ok=True)

    doc_score_rows: list[dict[str, Any]] = []
    section_rows: list[dict[str, Any]] = []
    variable_rows: list[dict[str, Any]] = []

    jobs = [(record.doc_key, record.blocks) for record in records]
    batch_results = review_blocks_batch(
        jobs,
        config=config,
        llm_client_factory=lambda: llm_client,
        therapeutic_area=therapeutic_area,
        claims_store=claims_store,
        max_tokens=max_tokens,
        max_workers=max_workers,
    )
    records_by_key = {record.doc_key: record for record in records}
    for batch_result in batch_results:
        record = records_by_key[batch_result.doc_key]
        if batch_result.error:
            logger.exception("Review failed for %s: %s", record.doc_key, batch_result.error)
            doc_score_rows.append(_failed_document_row(record, batch_result.error))
            continue
        result = batch_result.review
        doc_score_rows.append(_document_score_row(record, result, config))
        section_rows.extend(_section_rows(record, result, config))
        variable_rows.extend(_variable_rows(record, result))

    doc_score_rows.sort(key=lambda row: row["doc_key"])
    section_rows.sort(key=lambda row: (row["doc_key"], row["section_name"]))
    variable_rows.sort(key=lambda row: (row["doc_key"], row["section_name"], row["variable_name"]))

    _write_csv(output_path / "document_scores.csv", doc_score_rows, DOCUMENT_SCORE_COLUMNS)
    _write_csv(output_path / "section_grades.csv", section_rows, SECTION_GRADE_COLUMNS)
    _write_csv(output_path / "variable_grades.csv", variable_rows, VARIABLE_GRADE_COLUMNS)
    _write_summary(output_path / "summary.csv", doc_score_rows, section_rows, header)
    _write_manifest(
        output_path / "manifest.json",
        input_path=input_path,
        blocks_csv=blocks_csv,
        header=header,
        provider=provider,
        model=llm_client.model,
        max_workers=max_workers,
        max_tokens=max_tokens,
        doc_score_rows=doc_score_rows,
    )


def _resolve_header_from_package(
    document_rows: list[dict[str, Any]],
    therapeutic_area: str | None,
) -> dict[str, Any]:
    headers = {
        (row.get("org"), row.get("source_type"), row.get("intervention_class"))
        for row in document_rows
        if row.get("org") and row.get("source_type") and row.get("intervention_class")
    }
    if not headers:
        raise ValueError(
            "documents.csv has no header columns (org, source_type, intervention_class). "
            "Re-run the chunker with the current version."
        )
    if len(headers) > 1:
        raise ValueError(f"Package contains multiple headers: {sorted(headers)}. Split before reviewing.")
    org, source_type, intervention_class = next(iter(headers))
    return {
        "org": org,
        "source_type": source_type,
        "intervention_class": intervention_class,
        "therapeutic_area": therapeutic_area or "",
    }


def _build_document_records(
    document_rows: list[dict[str, Any]],
    block_rows: list[dict[str, Any]],
    header: dict[str, Any],
) -> list[_DocumentRecord]:
    blocks_by_doc = _blocks_by_doc(block_rows)
    records: list[_DocumentRecord] = []
    for row in document_rows:
        if row.get("parse_status") != "ok" or row.get("mapping_status") != "ok":
            continue
        doc_key = row.get("doc_key", "")
        doc_blocks = blocks_by_doc.get(doc_key, [])
        if not doc_blocks:
            continue
        records.append(
            _DocumentRecord(
                doc_key=doc_key,
                header=header,
                file_name=row.get("file_name", ""),
                blocks=doc_blocks,
            )
        )
    return records


def _blocks_by_doc(block_rows: list[dict[str, Any]]) -> dict[str, list[ContentBlock]]:
    grouped: dict[str, list[ContentBlock]] = defaultdict(list)
    for row in block_rows:
        block = _row_to_content_block(row)
        grouped[row["doc_key"]].append(block)
    for blocks in grouped.values():
        blocks.sort(key=lambda block: block.ordinal)
    return dict(grouped)


def _row_to_content_block(row: dict[str, Any]) -> ContentBlock:
    return ContentBlock(
        id=row["block_id"],
        doc_id=row["doc_key"],
        ordinal=int(row["ordinal"]),
        block_type=row["block_type"],
        content=row.get("content", ""),
        heading_stack=_json_list(row.get("heading_stack_json")),
        structural_meta=_json_object(row.get("structural_meta_json")),
        style_hint=_json_object(row.get("style_hint_json")),
        section_label=row.get("section_label") or None,
        label_confidence=row.get("label_confidence") or None,
        org=row.get("org") or None,
        source_type=row.get("source_type") or None,
        intervention_class=row.get("intervention_class") or None,
        therapeutic_area=row.get("therapeutic_area") or None,
    )


def _document_score_row(
    record: _DocumentRecord,
    result: ReviewResult,
    config: ReviewConfig,
) -> dict[str, Any]:
    sections_present = sum(1 for grade in result.section_grades if grade.is_present)
    return {
        "doc_key": record.doc_key,
        **record.header,
        "file_name": record.file_name,
        "overall_grade": result.overall_grade,
        "weighted_score": _weighted_score(result.section_grades, config),
        "sections_total": len(config.sections),
        "sections_present": sections_present,
        "sections_missing": len(config.sections) - sections_present,
        "top_issues_json": json.dumps(result.top_issues, ensure_ascii=False),
        "review_status": "ok",
        "review_error": "",
    }


def _failed_document_row(record: _DocumentRecord, error: str) -> dict[str, Any]:
    return {
        "doc_key": record.doc_key,
        **record.header,
        "file_name": record.file_name,
        "overall_grade": "",
        "weighted_score": "",
        "sections_total": "",
        "sections_present": "",
        "sections_missing": "",
        "top_issues_json": "[]",
        "review_status": "error",
        "review_error": error,
    }


def _section_rows(
    record: _DocumentRecord,
    result: ReviewResult,
    config: ReviewConfig,
) -> list[dict[str, Any]]:
    weight_by_section = {spec.name: spec.weight for spec in config.sections}
    rows: list[dict[str, Any]] = []
    for grade in result.section_grades:
        rows.append(
            {
                "doc_key": record.doc_key,
                **record.header,
                "section_name": grade.section_name,
                "weight": weight_by_section.get(grade.section_name, 0.0),
                "grade": grade.grade,
                "score": GRADE_TO_SCORE.get(grade.grade, ""),
                "is_present": grade.is_present,
                "missing_variables_json": json.dumps(grade.missing_variables, ensure_ascii=False),
                "issues_json": json.dumps(grade.issues, ensure_ascii=False),
                "recommendation": grade.recommendation,
                "variable_grades_count": len(grade.variable_grades),
            }
        )
    return rows


def _variable_rows(
    record: _DocumentRecord,
    result: ReviewResult,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for section_grade in result.section_grades:
        for variable in section_grade.variable_grades:
            rows.append(
                {
                    "doc_key": record.doc_key,
                    **record.header,
                    "section_name": section_grade.section_name,
                    "variable_name": variable.variable_name,
                    "grade": variable.grade,
                    "score": GRADE_TO_SCORE.get(variable.grade, ""),
                    "issues_json": json.dumps(variable.issues, ensure_ascii=False),
                    "recommendation": variable.recommendation,
                    "block_ids_json": json.dumps(variable.block_ids, ensure_ascii=False),
                }
            )
    return rows


def _weighted_score(
    section_grades: list[SectionGrade],
    config: ReviewConfig,
) -> float | str:
    grades_by_section = {grade.section_name: grade.grade for grade in section_grades}
    weighted = 0.0
    applied = 0.0
    for spec in config.sections:
        grade = grades_by_section.get(spec.name)
        if grade not in GRADE_TO_SCORE:
            continue
        weighted += GRADE_TO_SCORE[grade] * spec.weight
        applied += spec.weight
    if applied == 0:
        return ""
    return round(weighted / applied, 3)


def _write_manifest(
    path: Path,
    *,
    input_path: Path,
    blocks_csv: Path,
    header: dict[str, Any],
    provider: str,
    model: str,
    max_workers: int,
    max_tokens: int,
    doc_score_rows: list[dict[str, Any]],
) -> None:
    status_counts = Counter(row["review_status"] for row in doc_score_rows)
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "org": header["org"],
        "source_type": header["source_type"],
        "intervention_class": header["intervention_class"],
        "therapeutic_area": header.get("therapeutic_area", ""),
        "provider": provider,
        "model": model,
        "max_workers": max_workers,
        "max_tokens": max_tokens,
        "input_chunker_package": str(input_path),
        "input_content_blocks_sha256": _sha256_file(blocks_csv),
        "documents_total": len(doc_score_rows),
        "documents_reviewed": status_counts["ok"],
        "documents_failed": status_counts["error"],
    }
    with path.open("w", encoding="utf-8") as manifest_file:
        json.dump(manifest, manifest_file, indent=2, sort_keys=True)
        manifest_file.write("\n")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as binary_file:
        for chunk in iter(lambda: binary_file.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_summary(
    path: Path,
    doc_score_rows: list[dict[str, Any]],
    section_rows: list[dict[str, Any]],
    header: dict[str, Any],
) -> None:
    status_counts = Counter(row["review_status"] for row in doc_score_rows)
    grade_counts = Counter(row["overall_grade"] for row in doc_score_rows if row["overall_grade"])
    section_grade_counts = Counter(row["grade"] for row in section_rows)
    scored = [row["weighted_score"] for row in doc_score_rows if isinstance(row["weighted_score"], (int, float))]
    avg_score = round(sum(scored) / len(scored), 3) if scored else ""

    summary_rows = [
        {"metric": "org", "value": header["org"]},
        {"metric": "source_type", "value": header["source_type"]},
        {"metric": "intervention_class", "value": header["intervention_class"]},
        {"metric": "therapeutic_area", "value": header.get("therapeutic_area", "")},
        {"metric": "documents_total", "value": len(doc_score_rows)},
        {"metric": "documents_reviewed", "value": status_counts["ok"]},
        {"metric": "documents_failed", "value": status_counts["error"]},
        {"metric": "average_weighted_score", "value": avg_score},
        {"metric": "sections_total", "value": len(section_rows)},
    ]
    for grade in ["A", "B", "C", "D", "F", "N/A"]:
        summary_rows.append(
            {"metric": f"documents_grade_{grade}", "value": grade_counts.get(grade, 0)}
        )
        summary_rows.append(
            {"metric": f"sections_grade_{grade}", "value": section_grade_counts.get(grade, 0)}
        )
    _write_csv(path, summary_rows, ["metric", "value"])


def _read_csv(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8", newline="") as csv_file:
        return list(csv.DictReader(csv_file))


def _write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def _json_list(value: Any) -> list:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return []
    return parsed if isinstance(parsed, list) else []


def _json_object(value: Any) -> dict:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _api_key_env_var(provider: str) -> str:
    return "ANTHROPIC_API_KEY" if provider.lower() == "anthropic" else "OPENAI_API_KEY"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export a PD Reviewer package from a chunker package."
    )
    parser.add_argument("input_dir", help="Folder containing a parsed + mapped chunker package")
    parser.add_argument("output_dir", help="Folder where review CSVs are written")
    parser.add_argument("--therapeutic-area", default=None)
    parser.add_argument(
        "--claims-dir",
        default=None,
        help="Folder of evidence claims.jsonl files. If provided, the grader uses "
        "matching claims as additional signal.",
    )
    parser.add_argument("--provider", choices=["openai", "anthropic"], default="openai")
    parser.add_argument("--model", default=None)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_OUTPUT_TOKENS)
    args = parser.parse_args()
    if args.model is None:
        args.model = default_model_for_provider(args.provider)
    return args


if __name__ == "__main__":
    args = _parse_args()
    export_review_package(
        args.input_dir,
        args.output_dir,
        provider=args.provider,
        model=args.model,
        api_key=args.api_key,
        max_workers=args.max_workers,
        max_tokens=args.max_tokens,
        therapeutic_area=args.therapeutic_area,
        claims_dir=args.claims_dir,
    )
