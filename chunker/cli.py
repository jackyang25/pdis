"""CLI: parse (and optionally map) a folder of documents into chunker package tables.

Inputs (header):
    --org / --source-type / --intervention      identifies document type
    --therapeutic-area                          optional, stamped on every row

The chunker config is resolved from (org, source_type, intervention) via the
shared registry. Every output row (documents.csv, content_blocks.csv,
content_blocks.jsonl) carries the full four-field header as provenance.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from llm_client import create_llm_client, default_model_for_provider  # noqa: E402

from .models import blocks_to_dicts, find_config  # noqa: E402
from .pipeline import DEFAULT_MAX_OUTPUT_TOKENS, run_pipeline_batch  # noqa: E402


HEADER_COLUMNS = ["org", "source_type", "intervention_class", "therapeutic_area"]

DOCUMENT_COLUMNS = [
    "doc_key",
    *HEADER_COLUMNS,
    "file_name",
    "relative_path",
    "source_file",
    "doc_format",
    "parse_status",
    "parse_error",
    "mapping_status",
    "mapping_error",
    "total_blocks",
    "heading_blocks",
    "paragraph_blocks",
    "table_row_blocks",
]

BLOCK_COLUMNS = [
    "block_id",
    "doc_key",
    *HEADER_COLUMNS,
    "ordinal",
    "block_type",
    "content",
    "heading_stack_json",
    "structural_meta_json",
    "style_hint_json",
    "section_label",
    "label_confidence",
]


def export_chunker_package(
    input_dir: str,
    output_dir: str,
    *,
    org: str,
    source_type: str,
    intervention_class: str,
    therapeutic_area: str | None = None,
    map_blocks: bool = False,
    provider: str = "openai",
    model: str | None = None,
    api_key: str | None = None,
    max_workers: int = 4,
    max_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
) -> None:
    """Parse, and optionally map, documents into reusable package tables."""
    input_path = Path(input_dir).expanduser().resolve()
    output_path = Path(output_dir).expanduser().resolve()
    if not input_path.exists() or not input_path.is_dir():
        raise ValueError(f"input_dir must be an existing directory: {input_path}")
    if map_blocks:
        api_key = api_key or os.getenv(_api_key_env_var(provider))
        if not api_key:
            raise ValueError(
                f"api key is required for --map. Set {_api_key_env_var(provider)} "
                "or pass --api-key."
            )

    config = find_config(org, source_type, intervention_class)
    header = _make_header(org, source_type, intervention_class, therapeutic_area)

    output_path.mkdir(parents=True, exist_ok=True)
    doc_files = _input_files(input_path)
    used_doc_keys: set[str] = set()
    document_jobs = [
        {
            "file_path": file_path,
            "relative_path": file_path.relative_to(input_path),
            "doc_key": _unique_doc_key(file_path.relative_to(input_path), used_doc_keys),
        }
        for file_path in doc_files
    ]

    pipeline_jobs = [(str(job["file_path"]), job["doc_key"]) for job in document_jobs]

    def factory():
        return create_llm_client(provider=provider, api_key=api_key, model=model)

    pipeline_results = run_pipeline_batch(
        pipeline_jobs,
        config=config if map_blocks else None,
        llm_client_factory=factory if map_blocks else None,
        max_tokens=max_tokens,
        max_workers=max_workers,
    )

    document_rows: list[dict[str, Any]] = []
    block_rows: list[dict[str, Any]] = []
    block_jsonl_rows: list[dict[str, Any]] = []
    for job, pipeline_result in zip(document_jobs, pipeline_results):
        row_set = _process_pipeline_result(
            job=job,
            input_path=input_path,
            header=header,
            pipeline_result=pipeline_result,
            map_requested=map_blocks,
        )
        document_rows.append(row_set["document_row"])
        block_rows.extend(row_set["block_rows"])
        block_jsonl_rows.extend(row_set["block_jsonl_rows"])

    _write_csv(output_path / "documents.csv", document_rows, DOCUMENT_COLUMNS)
    _write_csv(output_path / "content_blocks.csv", block_rows, BLOCK_COLUMNS)
    _write_jsonl(output_path / "content_blocks.jsonl", block_jsonl_rows)
    _write_summary(output_path / "summary.csv", document_rows, block_rows, header)


def _process_pipeline_result(
    *,
    job: dict[str, Any],
    input_path: Path,
    header: dict[str, Any],
    pipeline_result,
    map_requested: bool,
) -> dict[str, Any]:
    file_path = job["file_path"]
    doc_key = job["doc_key"]
    document_row = _base_document_row(file_path, input_path, doc_key, header)

    if pipeline_result.parse_error:
        return {
            "document_row": {
                **document_row,
                "parse_status": "error",
                "parse_error": pipeline_result.parse_error,
                "mapping_status": "not_run",
                "mapping_error": "",
                "total_blocks": 0,
                "heading_blocks": 0,
                "paragraph_blocks": 0,
                "table_row_blocks": 0,
            },
            "block_rows": [],
            "block_jsonl_rows": [],
        }

    if not map_requested:
        mapping_status = "not_requested"
        mapping_error = ""
    elif pipeline_result.mapping_error:
        mapping_status = "error"
        mapping_error = pipeline_result.mapping_error
    else:
        mapping_status = "ok"
        mapping_error = ""

    block_dicts = blocks_to_dicts(pipeline_result.blocks)
    block_counts = Counter(block["block_type"] for block in block_dicts)
    return {
        "document_row": {
            **document_row,
            "parse_status": "ok",
            "parse_error": "",
            "mapping_status": mapping_status,
            "mapping_error": mapping_error,
            "total_blocks": len(block_dicts),
            "heading_blocks": block_counts["heading"],
            "paragraph_blocks": block_counts["paragraph"],
            "table_row_blocks": block_counts["table_row"],
        },
        "block_rows": [_block_row(block, doc_key, header) for block in block_dicts],
        "block_jsonl_rows": [
            {
                "doc_key": doc_key,
                **header,
                "source_file": str(file_path),
                **block,
            }
            for block in block_dicts
        ],
    }


def _input_files(input_path: Path) -> list[Path]:
    return sorted(
        file_path
        for file_path in input_path.rglob("*")
        if file_path.is_file()
        and file_path.suffix.lower() in {".docx", ".pdf"}
        and not file_path.name.startswith("~$")
    )


def _unique_doc_key(relative_path: Path, used_doc_keys: set[str]) -> str:
    base_key = _slugify(relative_path.with_suffix("").as_posix())
    doc_key = base_key
    suffix = 2
    while doc_key in used_doc_keys:
        doc_key = f"{base_key}_{suffix}"
        suffix += 1
    used_doc_keys.add(doc_key)
    return doc_key


def _slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_")
    return slug or "document"


def _make_header(
    org: str, source_type: str, intervention_class: str, therapeutic_area: str | None
) -> dict[str, Any]:
    return {
        "org": org,
        "source_type": source_type,
        "intervention_class": intervention_class,
        "therapeutic_area": therapeutic_area or "",
    }


def _base_document_row(
    file_path: Path,
    input_path: Path,
    doc_key: str,
    header: dict[str, Any],
) -> dict[str, Any]:
    relative_path = file_path.relative_to(input_path)
    return {
        "doc_key": doc_key,
        **header,
        "file_name": file_path.name,
        "relative_path": relative_path.as_posix(),
        "source_file": str(file_path),
        "doc_format": file_path.suffix.lower().removeprefix("."),
    }


def _block_row(block: dict[str, Any], doc_key: str, header: dict[str, Any]) -> dict[str, Any]:
    return {
        "block_id": block["id"],
        "doc_key": doc_key,
        **header,
        "ordinal": block["ordinal"],
        "block_type": block["block_type"],
        "content": block["content"],
        "heading_stack_json": _json_value(block["heading_stack"]),
        "structural_meta_json": _json_value(block["structural_meta"]),
        "style_hint_json": _json_value(block["style_hint"]),
        "section_label": block["section_label"],
        "label_confidence": block["label_confidence"],
    }


def _json_value(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as jsonl_file:
        for row in rows:
            jsonl_file.write(json.dumps(row, ensure_ascii=False) + "\n")


def _write_summary(
    path: Path,
    document_rows: list[dict[str, Any]],
    block_rows: list[dict[str, Any]],
    header: dict[str, Any],
) -> None:
    status_counts = Counter(row["parse_status"] for row in document_rows)
    mapping_counts = Counter(row["mapping_status"] for row in document_rows)
    block_counts = Counter(row["block_type"] for row in block_rows)
    summary_rows = [
        {"metric": "org", "value": header["org"]},
        {"metric": "source_type", "value": header["source_type"]},
        {"metric": "intervention_class", "value": header["intervention_class"]},
        {"metric": "therapeutic_area", "value": header.get("therapeutic_area", "")},
        {"metric": "documents_total", "value": len(document_rows)},
        {"metric": "documents_parsed", "value": status_counts["ok"]},
        {"metric": "documents_failed", "value": status_counts["error"]},
        {
            "metric": "documents_mapping_not_requested",
            "value": mapping_counts["not_requested"],
        },
        {"metric": "documents_mapped", "value": mapping_counts["ok"]},
        {"metric": "documents_mapping_failed", "value": mapping_counts["error"]},
        {"metric": "blocks_total", "value": len(block_rows)},
        {"metric": "heading_blocks", "value": block_counts["heading"]},
        {"metric": "paragraph_blocks", "value": block_counts["paragraph"]},
        {"metric": "table_row_blocks", "value": block_counts["table_row"]},
    ]
    _write_csv(path, summary_rows, ["metric", "value"])


def _api_key_env_var(provider: str) -> str:
    return "ANTHROPIC_API_KEY" if provider.lower() == "anthropic" else "OPENAI_API_KEY"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export a folder of documents into chunker package tables."
    )
    parser.add_argument("input_dir", help="Folder containing .docx / .pdf files")
    parser.add_argument("output_dir", help="Folder where package files are written")
    parser.add_argument("--org", required=True, help="e.g., gates, who")
    parser.add_argument("--source-type", required=True, help="e.g., tpp, ppc")
    parser.add_argument("--intervention", required=True, help="e.g., vaccine, drug")
    parser.add_argument("--therapeutic-area", default=None, help="Optional; stamped on outputs")
    parser.add_argument("--map", action="store_true", dest="map_blocks", help="Run mapper")
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
    export_chunker_package(
        args.input_dir,
        args.output_dir,
        org=args.org,
        source_type=args.source_type,
        intervention_class=args.intervention,
        therapeutic_area=args.therapeutic_area,
        map_blocks=args.map_blocks,
        provider=args.provider,
        model=args.model,
        api_key=args.api_key,
        max_workers=args.max_workers,
        max_tokens=args.max_tokens,
    )
