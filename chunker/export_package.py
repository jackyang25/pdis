from __future__ import annotations

import argparse
import csv
import json
import os
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

try:
    from .llm_client import create_llm_client, default_model_for_provider
    from .mapper import label_blocks
    from .models import blocks_to_dicts, load_config
    from .parser import parse_document
except ImportError:  # pragma: no cover - supports running as a script
    from llm_client import create_llm_client, default_model_for_provider
    from mapper import label_blocks
    from models import blocks_to_dicts, load_config
    from parser import parse_document


CONFIG_BY_TPP_TYPE = {
    "vaccine": "tpp_vaccine.yaml",
    "drug": "tpp_drug.yaml",
    "diagnostic": "tpp_diagnostic.yaml",
    "device": "tpp_device.yaml",
}

DOCUMENT_COLUMNS = [
    "doc_key",
    "tpp_type",
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
    "tpp_type",
    "ordinal",
    "source_type",
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
    map_blocks: bool = False,
    provider: str = "openai",
    model: str | None = None,
    api_key: str | None = None,
    max_workers: int = 4,
    tpp_type: str | None = None,
) -> None:
    """Parse, and optionally map, DOCX files into reusable package tables."""
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

    output_path.mkdir(parents=True, exist_ok=True)
    docx_files = _docx_files(input_path)
    document_rows: list[dict[str, Any]] = []
    block_rows: list[dict[str, Any]] = []
    block_jsonl_rows: list[dict[str, Any]] = []
    used_doc_keys: set[str] = set()
    document_jobs = []

    for file_path in docx_files:
        relative_path = file_path.relative_to(input_path)
        document_jobs.append(
            {
                "file_path": file_path,
                "relative_path": relative_path,
                "tpp_type": tpp_type or _tpp_type(relative_path),
                "doc_key": _unique_doc_key(relative_path, used_doc_keys),
            }
        )

    worker_count = max(1, min(max_workers, len(document_jobs) or 1))
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        results = list(
            executor.map(
                lambda job: _process_document(
                    job=job,
                    input_path=input_path,
                    map_blocks=map_blocks,
                    provider=provider,
                    model=model,
                    api_key=api_key,
                ),
                document_jobs,
            )
        )

    for result in results:
        document_rows.append(result["document_row"])
        block_rows.extend(result["block_rows"])
        block_jsonl_rows.extend(result["block_jsonl_rows"])

    _write_csv(output_path / "documents.csv", document_rows, DOCUMENT_COLUMNS)
    _write_csv(output_path / "content_blocks.csv", block_rows, BLOCK_COLUMNS)
    _write_jsonl(output_path / "content_blocks.jsonl", block_jsonl_rows)
    _write_summary(output_path / "summary.csv", document_rows, block_rows)


def _process_document(
    *,
    job: dict[str, Any],
    input_path: Path,
    map_blocks: bool,
    provider: str,
    model: str | None,
    api_key: str | None,
) -> dict[str, Any]:
    file_path = job["file_path"]
    tpp_type = job["tpp_type"]
    doc_key = job["doc_key"]
    document_row = _base_document_row(file_path, input_path, doc_key, tpp_type)

    try:
        blocks = parse_document(str(file_path), doc_key)
    except Exception as exc:
        return {
            "document_row": {
                **document_row,
                "parse_status": "error",
                "parse_error": str(exc),
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

    mapping_status = "not_requested"
    mapping_error = ""
    if map_blocks:
        try:
            if api_key is None:
                raise ValueError("api_key is required for mapping")
            config = _config_for_tpp_type(tpp_type)
            llm_client = create_llm_client(provider=provider, api_key=api_key, model=model)
            blocks = label_blocks(blocks, config, llm_client)
            mapping_status = "ok"
        except Exception as exc:
            mapping_status = "error"
            mapping_error = str(exc)

    block_dicts = blocks_to_dicts(blocks)
    source_counts = Counter(block["source_type"] for block in block_dicts)
    return {
        "document_row": {
            **document_row,
            "parse_status": "ok",
            "parse_error": "",
            "mapping_status": mapping_status,
            "mapping_error": mapping_error,
            "total_blocks": len(block_dicts),
            "heading_blocks": source_counts["heading"],
            "paragraph_blocks": source_counts["paragraph"],
            "table_row_blocks": source_counts["table_row"],
        },
        "block_rows": [_block_row(block, doc_key, tpp_type) for block in block_dicts],
        "block_jsonl_rows": [
            {
                "doc_key": doc_key,
                "tpp_type": tpp_type,
                "source_file": str(file_path),
                **block,
            }
            for block in block_dicts
        ],
    }


def _config_for_tpp_type(tpp_type: str):
    config_file_name = CONFIG_BY_TPP_TYPE.get(tpp_type)
    if config_file_name is None:
        raise ValueError(f"No chunker config for tpp_type: {tpp_type}")

    config_path = Path(__file__).parent / "configs" / config_file_name
    return load_config(str(config_path))


def _docx_files(input_path: Path) -> list[Path]:
    return sorted(
        file_path
        for file_path in input_path.rglob("*.docx")
        if file_path.is_file() and not file_path.name.startswith("~$")
    )


def _tpp_type(relative_path: Path) -> str:
    if len(relative_path.parts) <= 1:
        return "unknown"
    return relative_path.parts[0]


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


def _base_document_row(
    file_path: Path,
    input_path: Path,
    doc_key: str,
    tpp_type: str,
) -> dict[str, Any]:
    relative_path = file_path.relative_to(input_path)
    return {
        "doc_key": doc_key,
        "tpp_type": tpp_type,
        "file_name": file_path.name,
        "relative_path": relative_path.as_posix(),
        "source_file": str(file_path),
        "doc_format": file_path.suffix.lower().removeprefix("."),
    }


def _block_row(block: dict[str, Any], doc_key: str, tpp_type: str) -> dict[str, Any]:
    return {
        "block_id": block["id"],
        "doc_key": doc_key,
        "tpp_type": tpp_type,
        "ordinal": block["ordinal"],
        "source_type": block["source_type"],
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
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
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
) -> None:
    tpp_type_counts = Counter(row["tpp_type"] for row in document_rows)
    status_counts = Counter(row["parse_status"] for row in document_rows)
    mapping_counts = Counter(row["mapping_status"] for row in document_rows)
    source_counts = Counter(row["source_type"] for row in block_rows)
    summary_rows = [
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
        {"metric": "heading_blocks", "value": source_counts["heading"]},
        {"metric": "paragraph_blocks", "value": source_counts["paragraph"]},
        {"metric": "table_row_blocks", "value": source_counts["table_row"]},
    ]
    for tpp_type in sorted(tpp_type_counts):
        summary_rows.append(
            {"metric": f"documents_{tpp_type}", "value": tpp_type_counts[tpp_type]}
        )
    _write_csv(path, summary_rows, ["metric", "value"])


def _api_key_env_var(provider: str) -> str:
    return "ANTHROPIC_API_KEY" if provider.lower() == "anthropic" else "OPENAI_API_KEY"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export a folder of DOCX files into chunker package tables."
    )
    parser.add_argument("input_dir", help="Folder containing DOCX files by type subfolder")
    parser.add_argument("output_dir", help="Folder where package CSV/JSONL files are written")
    parser.add_argument(
        "--map",
        action="store_true",
        dest="map_blocks",
        help="Run mapper before export",
    )
    parser.add_argument("--provider", choices=["openai", "anthropic"], default="openai")
    parser.add_argument("--model", default=None)
    parser.add_argument("--api-key", default=None)
    parser.add_argument(
        "--tpp-type",
        choices=sorted(CONFIG_BY_TPP_TYPE),
        default=None,
        help="Override TPP type for all input documents",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=4,
        help="Maximum documents to process concurrently",
    )
    args = parser.parse_args()
    if args.model is None:
        args.model = default_model_for_provider(args.provider)
    return args


if __name__ == "__main__":
    args = _parse_args()
    export_chunker_package(
        args.input_dir,
        args.output_dir,
        map_blocks=args.map_blocks,
        provider=args.provider,
        model=args.model,
        api_key=args.api_key,
        max_workers=args.max_workers,
        tpp_type=args.tpp_type,
    )
