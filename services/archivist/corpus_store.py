"""Read and write the reviewed corpus.

The corpus is a committed artifact, not a runtime index, and that follows from what it is
rather than from a preference for static files. Every row is a model's reading of a
confidential document, and no reader should be shown "24 months, cited to block b-0042"
until a person has read that line and agreed with it. A tool that extracted on demand
would put an unreviewed reading in front of someone at the moment they trusted it most.

The source documents are not in this repository and will not be: they are BMGF product
documents. So the usual test for a generated artifact - regenerate it and diff - cannot
run here. What runs instead is stronger in the way that matters: loading re-checks every
invariant the build enforced, including that each quote still appears verbatim in the
block text stored beside it. A hand-edited row cannot survive a load, which is the actual
risk with a file people will edit during review.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from services.archivist.models import Corpus, CorpusDocument, CorpusRecord

CORPUS_DIR = Path(__file__).resolve().parent / "corpus"
CORPUS_FILE = CORPUS_DIR / "corpus.json"
MANIFEST_FILE = CORPUS_DIR / "manifest.yaml"
BUILD_REPORT_FILE = CORPUS_DIR / "build_report.json"

#: Bumped when the artifact's shape changes in a way a reader must notice. A loader that
#: silently accepted an older shape would read absent fields as absent facts.
CORPUS_VERSION = 1


def corpus_exists(path: str | Path | None = None) -> bool:
    return Path(path or CORPUS_FILE).exists()


def load_corpus(path: str | Path | None = None) -> Corpus:
    """Load and fully re-validate the committed corpus.

    An absent file is an empty corpus rather than an error. The tool is registered before
    any archive is built, and "nothing has been indexed yet" is a state the interface has
    to be able to show; raising here would make the page fail instead of explain.
    """
    corpus_path = Path(path or CORPUS_FILE)
    if not corpus_path.exists():
        return Corpus()
    with corpus_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    version = data.get("version")
    if version != CORPUS_VERSION:
        raise ValueError(
            f"{corpus_path}: corpus version {version!r}, expected {CORPUS_VERSION}. "
            "Rebuild it rather than reading it with a loader that does not know its shape."
        )
    documents = tuple(
        CorpusDocument(**_only(row, CorpusDocument)) for row in data.get("documents", [])
    )
    records = tuple(
        CorpusRecord(**_only(row, CorpusRecord)) for row in data.get("records", [])
    )
    # Every invariant runs here: the provenance chain per record, the tag vocabularies,
    # exhaustiveness across the grid, and one row per question.
    return Corpus(
        documents=documents, records=records, built_at=str(data.get("built_at") or "")
    )


def write_corpus(corpus: Corpus, path: str | Path | None = None) -> Path:
    """Write the corpus as the committed artifact.

    Sorted by document then attribute then bound, so a rebuild that changed one reading
    produces a one-row diff rather than a reshuffled file. Review happens in that diff.
    """
    corpus_path = Path(path or CORPUS_FILE)
    corpus_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": CORPUS_VERSION,
        "built_at": corpus.built_at,
        "documents": [asdict(document) for document in corpus.documents],
        "records": [asdict(record) for record in _sorted_records(corpus)],
    }
    with corpus_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False, sort_keys=False)
        handle.write("\n")
    return corpus_path


def _sorted_records(corpus: Corpus) -> list[CorpusRecord]:
    order = {document.id: index for index, document in enumerate(corpus.documents)}
    return sorted(
        corpus.records,
        key=lambda record: (
            order.get(record.document_id, len(order)),
            record.attribute,
            record.bound,
            # Both halves of the condition, matching the key `Corpus` enforces
            # uniqueness on. Sorting by one of them left two rows that differ only in
            # the other free to swap places between builds, which is a diff nobody can
            # review.
            record.condition_attribute,
            record.condition_stated,
        ),
    )


def _only(row: dict, shape: type) -> dict:
    """Keep the fields the dataclass declares, and refuse a row carrying others.

    Refused rather than filtered: a field the shape does not declare is either a stale
    artifact from an older build or someone's note added by hand, and both should be seen
    rather than dropped on load.
    """
    declared = set(shape.__dataclass_fields__)
    unknown = sorted(set(row) - declared)
    if unknown:
        raise ValueError(f"{shape.__name__}: the artifact carries unknown fields {unknown}")
    return {key: value for key, value in row.items() if key in declared}
