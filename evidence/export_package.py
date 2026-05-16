"""CLI: run the evidence pipeline against one or more documents.

Mirrors chunker/export_package.py shape: input directory of source documents
+ config + LLM config → output directory with claims.csv and claims.jsonl.

No persistent store. Each run is an independent input → output transformation.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .llm_client import (
    DEFAULT_MAX_OUTPUT_TOKENS,
    create_llm_client,
    default_model_for_provider,
)
from .models import Claim, load_config
from .pipeline import (
    EXTRACTORS,
    default_source_id_from_path,
    run_pipeline,
)


logger = logging.getLogger(__name__)


SUPPORTED_DOC_SUFFIXES = (".pdf", ".docx")


def main() -> None:
    args = _parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    config = load_config(args.config)
    api_key = args.api_key or os.environ.get(_api_key_env_var(args.provider))
    if not api_key:
        raise SystemExit(
            f"api key is required. Set {_api_key_env_var(args.provider)} or pass --api-key."
        )
    model = args.model or default_model_for_provider(args.provider)

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

    llm_client_factory = lambda: create_llm_client(args.provider, api_key, model)

    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        futures = [
            executor.submit(
                _run_one,
                path=path,
                config=config,
                source_type=args.source_type,
                intervention_class=args.intervention_class,
                therapeutic_area=args.therapeutic_area,
                llm_client_factory=llm_client_factory,
                max_tokens=args.max_tokens,
            )
            for path in doc_paths
        ]
        for future in futures:
            results.append(future.result())

    _write_outputs(output_dir, results)
    _log_summary(results)


def _run_one(
    *,
    path: Path,
    config,
    source_type: str,
    intervention_class: str | None,
    therapeutic_area: str | None,
    llm_client_factory,
    max_tokens: int,
) -> dict[str, Any]:
    source_id = default_source_id_from_path(str(path))
    doc_id = source_id
    try:
        llm_client = llm_client_factory()
        blocks, claims = run_pipeline(
            file_path=str(path),
            doc_id=doc_id,
            source_type=source_type,
            source_id=source_id,
            config=config,
            llm_client=llm_client,
            intervention_class=intervention_class,
            therapeutic_area=therapeutic_area,
            max_tokens=max_tokens,
        )
        return {
            "source_id": source_id,
            "file_name": path.name,
            "block_count": len(blocks),
            "claim_count": len(claims),
            "status": "ok",
            "error": None,
            "claims": claims,
        }
    except Exception as exc:
        logger.exception("Pipeline failed for %s", path)
        return {
            "source_id": source_id,
            "file_name": path.name,
            "block_count": 0,
            "claim_count": 0,
            "status": "error",
            "error": str(exc),
            "claims": [],
        }


def _write_outputs(output_dir: Path, results: list[dict[str, Any]]) -> None:
    claims_jsonl_path = output_dir / "claims.jsonl"
    claims_csv_path = output_dir / "claims.csv"
    summary_csv_path = output_dir / "summary.csv"

    all_claims: list[Claim] = []
    for result in results:
        all_claims.extend(result["claims"])

    # claims.jsonl
    with claims_jsonl_path.open("w", encoding="utf-8") as handle:
        for claim in all_claims:
            handle.write(json.dumps(asdict(claim), ensure_ascii=False))
            handle.write("\n")

    # claims.csv (flat)
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

    # summary.csv (per document)
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


def _api_key_env_var(provider: str) -> str:
    return "ANTHROPIC_API_KEY" if provider == "anthropic" else "OPENAI_API_KEY"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the evidence pipeline against a folder of source documents."
    )
    parser.add_argument("input_dir", help="Folder containing source documents (.pdf, .docx)")
    parser.add_argument("output_dir", help="Folder where claims.csv / claims.jsonl / summary.csv are written")
    parser.add_argument(
        "--config",
        required=True,
        help="Path to an evidence AttributeConfig YAML (e.g., evidence/configs/vaccine.yaml)",
    )
    parser.add_argument(
        "--source-type",
        choices=sorted(EXTRACTORS.keys()),
        default="product_profile",
        help="Which extractor to use. Only `product_profile` is wired today.",
    )
    parser.add_argument("--intervention-class", default=None)
    parser.add_argument("--therapeutic-area", default=None)
    parser.add_argument("--provider", choices=["openai", "anthropic"], default="anthropic")
    parser.add_argument("--model", default=None)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_OUTPUT_TOKENS)
    return parser.parse_args()


if __name__ == "__main__":
    main()
