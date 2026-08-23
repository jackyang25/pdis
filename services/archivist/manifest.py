"""What a person declares about each file before anything reads it.

The corpus is built from a folder of documents plus this manifest, and the split between
them is the one design decision in this file. A manifest row carries exactly the fields a
person reads off a cover page and whose error would otherwise be invisible - which
organisation wrote it, whether it is an iTPP or a cTPP, which intervention class and
indication. Everything else about a document is extracted from its prose and checked
against a quote.

That is not a preference for manual work. It is the difference between an error that
shows up and one that does not: a wrong shelf life is contradicted by the quote beside
it, while a cTPP mislabelled as an iTPP silently turns one candidate's commitment into a
class-level ambition in every row below it, and no downstream check would notice.

`file` is build input and stops here. It names a path on the machine that ran the build,
which is not a fact about the document, and a committed artifact carrying it would
describe someone's laptop.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from services.archivist.indexed_attributes import (
    MISSING_INDEXED_CLASSES,
    INDEXED_ATTRIBUTES,
)
from services.archivist.models import CorpusDocument
from services.chunker.models import find_config

MANIFEST_FIELDS = ("id", "file", "title", "org", "source_type", "intervention_class",
                   "indication")


@dataclass(frozen=True)
class ManifestEntry:
    """One declared document, and where to find it during the build."""

    id: str
    file: str
    title: str
    org: str
    source_type: str
    intervention_class: str
    indication: str

    def document(self) -> CorpusDocument:
        """The corpus's view of this entry, without the build-time path."""
        return CorpusDocument(
            id=self.id,
            title=self.title,
            org=self.org,
            intervention_class=self.intervention_class,
            indication=self.indication,
            source_type=self.source_type,
        )


def load_manifest(path: str | Path) -> tuple[ManifestEntry, ...]:
    """Read and validate a corpus manifest.

    Everything checkable is checked here, before a single model call is made. A build
    that fails on its fortieth document because one row named a document type chunker
    cannot parse has spent real money to learn something a file read would have told it.
    """
    manifest_path = Path(path)
    if not manifest_path.exists():
        raise LookupError(f"No corpus manifest at {manifest_path}")
    with manifest_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    rows = data.get("documents") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        raise ValueError(f"{manifest_path}: expected a `documents:` list")
    if not rows:
        # The shipped manifest is empty, and refusing it is right rather than building an
        # empty corpus: a corpus over no documents would be written, committed, and read
        # as an archive that holds nothing, which is not the same as one nobody has built.
        raise ValueError(
            f"{manifest_path} lists no documents yet. Add one row per document, then "
            "re-run with --dry-run to validate them before any model call."
        )

    entries: list[ManifestEntry] = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise ValueError(f"{manifest_path}: entry {index} is not a mapping")
        missing = [field for field in MANIFEST_FIELDS if not str(row.get(field, "")).strip()]
        if missing:
            raise ValueError(
                f"{manifest_path}: entry {index} is missing {', '.join(missing)}"
            )
        unknown = sorted(set(row) - set(MANIFEST_FIELDS))
        if unknown:
            # Refused rather than ignored: a field the manifest does not support is
            # someone declaring something they expect to be honoured.
            raise ValueError(
                f"{manifest_path}: entry {index} declares fields the manifest does not "
                f"support: {unknown}"
            )
        entry = ManifestEntry(**{field: str(row[field]).strip() for field in MANIFEST_FIELDS})
        if entry.intervention_class not in INDEXED_ATTRIBUTES:
            raise ValueError(
                f"{manifest_path}: {entry.id} is a {entry.intervention_class}, which has "
                f"no corpus columns declared. "
                f"{MISSING_INDEXED_CLASSES.get(entry.intervention_class, '')}".strip()
            )
        # Raises if the class or indication is not in the shared vocabulary.
        entry.document()
        try:
            find_config(entry.org, entry.source_type, entry.intervention_class)
        except LookupError as error:
            raise ValueError(
                f"{manifest_path}: {entry.id} cannot be parsed - {error}"
            ) from error
        entries.append(entry)

    for field in ("id", "file"):
        seen: dict[str, str] = {}
        for entry in entries:
            value = getattr(entry, field)
            if value in seen:
                raise ValueError(
                    f"{manifest_path}: two entries share the same {field} {value!r}"
                )
            seen[value] = entry.id
    return tuple(entries)


def resolve_source(entry: ManifestEntry, documents_dir: str | Path) -> Path:
    """The document file for one entry, inside the folder the build was given."""
    root = Path(documents_dir).resolve()
    path = (root / entry.file).resolve()
    if root not in path.parents:
        # A manifest is reviewed content, but it is still a file that names paths.
        raise ValueError(f"{entry.id}: {entry.file!r} points outside {root}")
    if not path.exists():
        raise LookupError(f"{entry.id}: no such document {path}")
    return path
