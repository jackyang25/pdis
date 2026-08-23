"""Build the reviewed Archivist corpus from a folder of documents and a manifest.

    .venv/bin/python scripts/build_archivist_corpus.py --documents ~/corpus-docs

The output is a committed artifact that a person reads before anyone relies on it, so this
script optimises for a reviewable diff and a report that says whether the build can be
trusted at all - not for being run often.

Three phases, each one flat pool of independent work. Flat rather than nested on purpose:
a pool over attributes inside a pool over documents multiplies into a concurrency nobody
declared, and it is the first thing to hit a provider rate limit.

    parse     one job per document, grouped by document type because chunker's batch
              entry point takes one parsing config at a time
    extract   one job per (document, attribute) - the finest independent unit, and the
              eight jobs for one document share a cached prompt prefix
    classify  one job per extracted value of a filterable column, reading the value
              alone rather than the document

The phases are ordered by dependency and nothing else. Extraction needs labelled blocks;
classification needs an extracted value. Neither needs anything from a sibling job, which
is why each phase is one pool rather than a pipeline per document.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.archivist.corpus_store import (  # noqa: E402
    BUILD_REPORT_FILE,
    CORPUS_FILE,
    MANIFEST_FILE,
    write_corpus,
)
from services.archivist.manifest import load_manifest, resolve_source  # noqa: E402
from services.archivist.models import Corpus, CorpusRecord  # noqa: E402
from services.archivist.stages.classifier import (  # noqa: E402
    ClassificationReport,
    classify_records,
)
from services.archivist.stages.extractor import (  # noqa: E402
    ExtractionReport,
    extract_attribute,
    prepare_document,
)
from services.chunker import run_pipeline_batch  # noqa: E402
from services.chunker.models import find_config  # noqa: E402
from shared.batching import map_ordered  # noqa: E402
from shared.openai_client import OpenAIClient  # noqa: E402

logger = logging.getLogger("build_archivist_corpus")

#: Fan-out per phase. Parsing is dominated by one mapper call per document; extraction and
#: classification are one call per job. Set below the provider's concurrency rather than at
#: it, because a build that trips a rate limit halfway leaves a partial artifact.
PARSE_WORKERS = 4
EXTRACT_WORKERS = 8
CLASSIFY_WORKERS = 8


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--documents",
        required=True,
        help="folder holding the source documents named by the manifest",
    )
    parser.add_argument("--manifest", default=str(MANIFEST_FILE))
    parser.add_argument("--out", default=str(CORPUS_FILE))
    parser.add_argument("--report", default=str(BUILD_REPORT_FILE))
    parser.add_argument(
        "--only",
        action="append",
        default=[],
        help="build one manifest id (repeatable). The result is a partial corpus and is "
        "written to --out only if you also pass --allow-partial.",
    )
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="write the corpus even when it holds fewer documents than the manifest "
        "declares, whether because of --only or because a document could not be read.",
    )
    parser.add_argument("--dry-run", action="store_true", help="validate inputs and stop")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    # Everything checkable is checked before a single model call: a build that fails on
    # its fortieth document because one manifest row named an unparseable type has spent
    # real money to learn what a file read would have said.
    entries = load_manifest(args.manifest)
    if args.only:
        wanted = set(args.only)
        unknown = sorted(wanted - {entry.id for entry in entries})
        if unknown:
            parser.error(f"--only names ids the manifest does not list: {unknown}")
        entries = tuple(entry for entry in entries if entry.id in wanted)
    sources = {entry.id: resolve_source(entry, args.documents) for entry in entries}
    logger.info("Manifest: %d documents, all resolved and parseable", len(entries))
    if args.dry_run:
        return 0

    factory = OpenAIClient
    client = factory()

    blocks_by_document, parse_failures = _parse(entries, sources, factory)
    records, extraction = _extract(entries, blocks_by_document, client)
    records, classification = _classify(records, entries, client)

    built = [entry for entry in entries if entry.id in blocks_by_document]
    corpus = Corpus(
        documents=tuple(entry.document() for entry in built),
        records=tuple(records),
        built_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )

    report = _report(corpus, parse_failures, extraction, classification)
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    _log_report(report)

    # One rule for one question: is this corpus every document the manifest declared?
    # `--only` and a failed parse both mean no, and both used to be treated differently -
    # the first refused to write and the second wrote a short corpus to the canonical path
    # and returned 1, which is a partial corpus committed as a complete one.
    declared = len(load_manifest(args.manifest))
    unparsed = sorted(entry.id for entry in entries if entry.id not in blocks_by_document)
    partial = len(built) < declared or bool(unparsed)
    if partial and not args.allow_partial:
        logger.warning(
            "Built %d of %d declared documents%s. Not writing %s: a partial corpus reads "
            "as a complete one, and every count this tool reports would be wrong by the "
            "documents it never saw. Pass --allow-partial to write it anyway.",
            len(built),
            declared,
            f" (could not read {', '.join(unparsed)})" if unparsed else "",
            args.out,
        )
        return 1
    write_corpus(corpus, args.out)
    logger.info("Wrote %s and %s", args.out, args.report)
    return 0 if not parse_failures else 1


def _parse(entries, sources, factory) -> tuple[dict, list[str]]:
    """Phase one: parse and section-label every document.

    Grouped by parsing config because that is what chunker's batch entry point takes. The
    grouping is not a parallelism decision - the pool is still flat within each group, and
    the groups run in sequence.
    """
    grouped: dict[tuple[str, str, str], list] = defaultdict(list)
    for entry in entries:
        grouped[(entry.org, entry.source_type, entry.intervention_class)].append(entry)

    blocks_by_document: dict[str, list] = {}
    failures: list[str] = []
    for key, group in grouped.items():
        config = find_config(*key)
        logger.info("Parsing %d %s documents", len(group), config.type_key)
        # One indication per call, because the header is stamped per batch. Grouping by
        # indication as well would fragment the batches for a field that costs nothing to
        # stamp afterwards, so the entries are batched per indication here.
        for indication in dict.fromkeys(entry.indication for entry in group):
            jobs_entries = [entry for entry in group if entry.indication == indication]
            results = run_pipeline_batch(
                [(str(sources[entry.id]), entry.id) for entry in jobs_entries],
                config=config,
                llm_client_factory=factory,
                max_workers=PARSE_WORKERS,
                indication=indication,
            )
            for entry, result in zip(jobs_entries, results):
                if result.parse_error:
                    failures.append(f"{entry.id}: parse failed - {result.parse_error}")
                    continue
                if result.mapping_error:
                    # Kept, not dropped. Unlabelled blocks still carry their text and
                    # heading path, so the reading is possible and only `section_label`
                    # is poorer. The failure is recorded so a reviewer knows why.
                    failures.append(
                        f"{entry.id}: section labels unavailable - {result.mapping_error}"
                    )
                blocks_by_document[entry.id] = result.blocks
    return blocks_by_document, failures


def _extract(entries, blocks_by_document, client) -> tuple[list[CorpusRecord], ExtractionReport]:
    """Phase two: one job per (document, attribute), in one flat pool."""
    jobs = []
    for entry in entries:
        blocks = blocks_by_document.get(entry.id)
        if not blocks:
            continue
        prepared = prepare_document(entry.document(), blocks)
        jobs.extend((prepared, column) for column in prepared.columns())
    logger.info("Extracting %d attribute readings", len(jobs))

    report = ExtractionReport()
    records: list[CorpusRecord] = []
    for job_records, job_report in map_ordered(
        jobs,
        lambda job: extract_attribute(job[0], job[1], client),
        workers=EXTRACT_WORKERS,
    ):
        records.extend(job_records)
        report.merge(job_report)
    return records, report


def _classify(records, entries, client) -> tuple[list[CorpusRecord], ClassificationReport]:
    """Phase three: tag the values of filterable columns.

    Grouped by intervention class because the tag vocabulary is declared per class. Within
    a class the pool is flat over values.
    """
    by_class: dict[str, str] = {entry.id: entry.intervention_class for entry in entries}
    report = ClassificationReport()
    out: list[CorpusRecord] = list(records)
    for intervention_class in dict.fromkeys(by_class.values()):
        indices = [
            index
            for index, record in enumerate(out)
            if by_class.get(record.document_id) == intervention_class
        ]
        subset, subset_report = classify_records(
            [out[index] for index in indices], intervention_class, client
        )
        for index, record in zip(indices, subset):
            out[index] = record
        report.merge(subset_report)
    logger.info("Classified %d values", report.tagged)
    return out, report


def _report(corpus, parse_failures, extraction, classification) -> dict:
    """What the build did, for the person who reviews the artifact.

    Separate from the corpus because it is a fact about the build, not about the archive.
    The two numbers that decide whether the artifact is usable - readings whose quote was
    not in the document, and readings that paraphrased their own quote - exist nowhere in
    the corpus, because a discarded reading leaves no row.
    """
    stated = [record for record in corpus.records if record.status == "stated"]
    return {
        "built_at": corpus.built_at,
        "documents": len(corpus.documents),
        "records": len(corpus.records),
        "parse_failures": parse_failures,
        "extraction": {
            "calls": extraction.calls,
            "values_kept": len(stated),
            "silent": extraction.silent,
            "uncertain": extraction.uncertain,
            "discarded_unverified_quote": extraction.unverified,
            "discarded_paraphrase": extraction.paraphrased,
            "no_answer": extraction.unanswered,
            "notes": extraction.notes,
        },
        "classification": {
            "calls": classification.calls,
            "tagged": classification.tagged,
            "untagged": classification.untagged,
            "notes": classification.notes,
        },
        "quantities_parsed": sum(1 for record in stated if record.magnitude is not None),
    }


def _log_report(report: dict) -> None:
    extraction = report["extraction"]
    logger.info(
        "Built %d documents, %d rows: %d values, %d silent, %d uncertain",
        report["documents"],
        report["records"],
        extraction["values_kept"],
        extraction["silent"],
        extraction["uncertain"],
    )
    discarded = extraction["discarded_unverified_quote"] + extraction["discarded_paraphrase"]
    if discarded:
        logger.warning(
            "Discarded %d readings that could not be verified against their document "
            "(%d unfound quotes, %d paraphrases). Read the notes before trusting this "
            "build.",
            discarded,
            extraction["discarded_unverified_quote"],
            extraction["discarded_paraphrase"],
        )
    for failure in report["parse_failures"]:
        logger.warning("%s", failure)


if __name__ == "__main__":
    raise SystemExit(main())
