"""Verify authored terminology citations against a downloaded NLM descriptor file.

Offline maintenance only: no runtime network calls, inferred mappings, or query
expansion. Run from the repository root with `python -m scripts.check_indication_mesh`.
"""

from __future__ import annotations

import argparse
import gzip
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from shared.vocabulary import IndicationDefinition, indication_definitions, intervention_classes


def verify_mesh(source: Path, entries: tuple[IndicationDefinition, ...]) -> list[str]:
    """Check the cited concept and exact entry term, not just its parent descriptor."""
    wanted = {entry.mesh_descriptor for entry in entries}
    concepts: dict[tuple[str, str], set[str]] = {}
    opener = gzip.open if source.suffix == ".gz" else open
    with opener(source, "rb") as handle:
        for _, record in ET.iterparse(handle, events=("end",)):
            if record.tag != "DescriptorRecord":
                continue
            descriptor = record.findtext("DescriptorUI")
            if descriptor in wanted:
                for concept in record.findall("ConceptList/Concept"):
                    concepts[(descriptor, concept.findtext("ConceptUI", ""))] = {
                        term.text or "" for term in concept.findall("TermList/Term/String")
                    }
            record.clear()
    errors = []
    for entry in entries:
        terms = concepts.get((entry.mesh_descriptor, entry.mesh_concept), set())
        if entry.mesh_term not in terms:
            errors.append(f"{entry.key}: cited descriptor/concept does not contain {entry.mesh_term!r}")
        # This is a catalog spelling check, never a runtime identity decision.
        key_from_term = re.sub(r"[^a-z0-9]+", "_", entry.mesh_term.lower()).strip("_")
        if entry.match == "exact" and entry.key != key_from_term:
            errors.append(f"{entry.key}: not the normalized spelling of its cited MeSH term")
        if entry.match == "narrower" and not entry.note.strip():
            errors.append(f"{entry.key}: narrower context requires an explicit scope note")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Official desc2026.xml or desc2026.gz")
    args = parser.parse_args()
    by_key = {}
    for intervention in sorted(intervention_classes()):
        for entry in indication_definitions(intervention):
            if entry.key in by_key and by_key[entry.key] != entry:
                raise ValueError(f"Conflicting definitions for {entry.key}")
            by_key[entry.key] = entry
    entries = tuple(by_key.values())
    errors = verify_mesh(args.source, entries)
    for error in errors:
        print(error)
    if errors:
        return 1
    narrower = [entry.key for entry in entries if entry.match == "narrower"]
    print(f"Verified {len(entries)} citations: {len(entries) - len(narrower)} exact terms, {len(narrower)} documented narrower contexts.")
    for key in narrower:
        print(f"  narrower: {key}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
