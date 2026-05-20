"""Read-side claims store.

A `ClaimsStore` is anything that answers questions like "give me the
claims for source X" or "give me all claims matching header Y". Today's
implementation reads a folder of `claims.jsonl` files. A future Delta /
Postgres implementation will satisfy the same Protocol and reviewer
(or any other consumer) won't notice the swap.

The folder layout the FileClaimsStore expects:
    <root>/
      run_001/
        claims.jsonl
        ...
      run_002/
        claims.jsonl
        ...

Or flat — any *.jsonl under the root. We scan recursively.
"""

from __future__ import annotations

import json
import logging
from dataclasses import fields
from pathlib import Path
from typing import Iterable, Protocol

from .models import Claim


logger = logging.getLogger(__name__)


class ClaimsStore(Protocol):
    """The read-side contract reviewer (and future consumers) depend on."""

    def get_by_source_id(self, source_id: str) -> list[Claim]:
        ...

    def get_by_attribute(
        self,
        attribute_ref: str,
        *,
        indication: str | None = None,
        exclude_source_id: str | None = None,
    ) -> list[Claim]:
        ...

    def get_by_header(
        self,
        *,
        org: str | None = None,
        source_type: str | None = None,
        intervention_class: str | None = None,
        indication: str | None = None,
        exclude_source_id: str | None = None,
    ) -> list[Claim]:
        ...


class FileClaimsStore:
    """ClaimsStore backed by a folder of `claims.jsonl` files.

    On init, scans the folder recursively and loads every claim into memory.
    Cheap for handfuls-of-thousands; switch to a real DB when that hurts.
    """

    def __init__(self, root: Path | str):
        self.root = Path(root).expanduser().resolve()
        self._claims: list[Claim] = list(_load_all(self.root))

    def __len__(self) -> int:
        return len(self._claims)

    def get_by_source_id(self, source_id: str) -> list[Claim]:
        return [c for c in self._claims if c.source_id == source_id]

    def get_by_attribute(
        self,
        attribute_ref: str,
        *,
        indication: str | None = None,
        exclude_source_id: str | None = None,
    ) -> list[Claim]:
        results = [c for c in self._claims if c.attribute_ref == attribute_ref]
        if indication is not None:
            results = [c for c in results if c.indication == indication]
        if exclude_source_id is not None:
            results = [c for c in results if c.source_id != exclude_source_id]
        return results

    def get_by_header(
        self,
        *,
        org: str | None = None,
        source_type: str | None = None,
        intervention_class: str | None = None,
        indication: str | None = None,
        exclude_source_id: str | None = None,
    ) -> list[Claim]:
        results = self._claims
        if org is not None:
            results = [c for c in results if c.org == org]
        if source_type is not None:
            results = [c for c in results if c.source_type == source_type]
        if intervention_class is not None:
            results = [c for c in results if c.intervention_class == intervention_class]
        if indication is not None:
            results = [c for c in results if c.indication == indication]
        if exclude_source_id is not None:
            results = [c for c in results if c.source_id != exclude_source_id]
        return results


def _load_all(root: Path) -> Iterable[Claim]:
    """Yield Claim records from every *.jsonl under root. Skip unreadable files."""
    if not root.exists() or not root.is_dir():
        return
    jsonl_files = sorted(root.rglob("*.jsonl"))
    if not jsonl_files:
        return
    field_names = {f.name for f in fields(Claim)}
    for path in jsonl_files:
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line_no, line in enumerate(handle, start=1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        logger.warning("Skipping malformed JSON: %s:%d", path, line_no)
                        continue
                    if not isinstance(data, dict):
                        continue
                    # Filter to known Claim fields (tolerate extra columns in source data)
                    cleaned = {k: v for k, v in data.items() if k in field_names}
                    # Backfill required fields missing on older JSONLs.
                    cleaned.setdefault("extracted_at", "")
                    try:
                        yield Claim(**cleaned)
                    except TypeError as exc:
                        logger.warning(
                            "Skipping record missing required fields in %s:%d (%s)",
                            path, line_no, exc,
                        )
        except OSError as exc:
            logger.warning("Could not read %s: %s", path, exc)
