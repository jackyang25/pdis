"""CLI: run the evidence pipeline against one or more documents.

Inputs (header):
    --org / --source-type / --intervention      identifies document type
    --therapeutic-area                          optional per-doc tag

Evidence config is resolved by `intervention` alone (the attribute namespace
is per product class, not per document format). The full header is stamped
on every output claim.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from llm_client import LLMClient  # noqa: E402

from .models import Claim, find_config  # noqa: E402
from .pipeline import (  # noqa: E402
    DEFAULT_MAX_OUTPUT_TOKENS,
    EXTRACTORS,
    default_source_id_from_path,
    run_pipeline_batch,
)


logger = logging.getLogger(__name__)


SUPPORTED_DOC_SUFFIXES = (".pdf", ".docx")


def main() -> None:
    args = _parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    config = find_config(args.intervention)

    api_key = args.api_key or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is required (or pass --api-key).")

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    doc_paths = sorted(
        path
        for path in input_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_DOC_SUFFIXES
    )
    if not doc_paths:
        raise SystemExit(f"No .pdf or .docx files found under {input_dir}")

    logger.info("Found %d documents under %s", len(doc_paths), input_dir)

    llm_client_factory = lambda: LLMClient(api_key=api_key)

    jobs = [(str(path), default_source_id_from_path(str(path))) for path in doc_paths]
    batch_results = run_pipeline_batch(
        jobs,
        config=config,
        llm_client_factory=llm_client_factory,
        org=args.org,
        source_type=args.source_type,
        therapeutic_area=args.therapeutic_area,
        source_kind=args.source_kind,
        max_tokens=args.max_tokens,
        max_workers=args.max_workers,
    )

    results: list[dict[str, Any]] = []
    for path, batch_result in zip(doc_paths, batch_results):
        if batch_result.error:
            logger.exception("Pipeline failed for %s: %s", path, batch_result.error)
        results.append(
            {
                "source_id": batch_result.source_id,
                "file_name": path.name,
                "block_count": len(batch_result.blocks),
                "claim_count": len(batch_result.claims),
                "status": "error" if batch_result.error else "ok",
                "error": batch_result.error,
                "claims": batch_result.claims,
            }
        )

    _write_outputs(output_dir, results)
    _log_summary(results)


def _write_outputs(output_dir: Path, results: list[dict[str, Any]]) -> None:
    claims_jsonl_path = output_dir / "claims.jsonl"
    claims_csv_path = output_dir / "claims.csv"
    summary_csv_path = output_dir / "summary.csv"

    all_claims: list[Claim] = []
    for result in results:
        all_claims.extend(result["claims"])

    with claims_jsonl_path.open("w", encoding="utf-8") as handle:
        for claim in all_claims:
            handle.write(json.dumps(asdict(claim), ensure_ascii=False))
            handle.write("\n")

    if all_claims:
        flat_rows = []
        for claim in all_claims:
            row = asdict(claim)
            row["source_locator_json"] = json.dumps(row.pop("source_locator"), ensure_ascii=False)
            flat_rows.append(row)
        fieldnames = list(flat_rows[0].keys())
        with claims_csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(flat_rows)

    with summary_csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["source_id", "file_name", "status", "block_count", "claim_count", "error"],
        )
        writer.writeheader()
        for result in results:
            writer.writerow(
                {
                    "source_id": result["source_id"],
                    "file_name": result["file_name"],
                    "status": result["status"],
                    "block_count": result["block_count"],
                    "claim_count": result["claim_count"],
                    "error": result["error"] or "",
                }
            )

    logger.info(
        "Wrote outputs to %s: %s, %s, %s",
        output_dir,
        claims_jsonl_path.name,
        claims_csv_path.name,
        summary_csv_path.name,
    )


def _log_summary(results: list[dict[str, Any]]) -> None:
    ok = sum(1 for r in results if r["status"] == "ok")
    err = len(results) - ok
    total_claims = sum(r["claim_count"] for r in results)
    logger.info(
        "Pipeline complete: %d documents ok, %d failed, %d total claims",
        ok, err, total_claims,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the evidence pipeline against a folder of source documents."
    )
    parser.add_argument("input_dir", help="Folder containing source documents (.pdf, .docx)")
    parser.add_argument("output_dir", help="Folder where outputs are written")
    parser.add_argument("--org", required=True)
    parser.add_argument("--source-type", required=True)
    parser.add_argument("--intervention", required=True)
    parser.add_argument("--therapeutic-area", default=None)
    if len(EXTRACTORS) > 1:
        parser.add_argument(
            "--source-kind",
            choices=sorted(EXTRACTORS.keys()),
            required=True,
            help="Which extractor to use.",
        )
    else:
        only_kind = next(iter(EXTRACTORS))
        parser.set_defaults(source_kind=only_kind)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_OUTPUT_TOKENS)
    return parser.parse_args()


if __name__ == "__main__":
    main()
