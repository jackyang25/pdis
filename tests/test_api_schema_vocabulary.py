"""Every closed vocabulary in the API response schema, against the domain that owns it.

The bug this exists for, and the reason it kept recurring. `api/schemas.py` declares 51
`Literal[...]` sets, each a hand-copied duplicate of a domain vocabulary. A value added to the
domain does not reach the copy, and nothing notices until a run produces that value: the whole
analysis succeeds, and then the response fails to serialise.

    1 validation error for DevelopmentProgramOut
    supporting_findings.0.development_records.0.record_type
      Input should be 'clinical_trial', 'compound_catalog', 'regulatory_label' or
      'regulatory_clearance' [input_value='announcement']

`announcement` had been a `DEVELOPMENT_RECORD_TYPES` member for as long as the announcement
reader existed. The schema listed four of the five.

This walks every Literal in the file and requires each to *equal* a domain vocabulary, or to be
named below as one the API owns. So a divergence fails here rather than on a user's run, and a
new Literal cannot be added without deciding which of the two it is.
"""

from __future__ import annotations

import pathlib
import re
import unittest

from services.scout import models as scout_models
from services.searcher.models import (
    DEVELOPMENT_RECORD_TYPES,
    FINDING_ROLES,
    INDICATOR_SPATIAL_TYPES,
    SAFETY_RECORD_TYPES,
    SAFETY_SOURCE_SYSTEMS,
    SOURCE_ROLES,
)
from shared.vocabulary import ENTITY_TYPES, EVIDENCE_CLASSES, EVIDENCE_DOMAINS

SCHEMA = pathlib.Path("api/schemas.py")


def domain_vocabularies() -> dict[str, frozenset[str]]:
    """Every closed set of strings the domain declares.

    Collected rather than listed, so a vocabulary added upstream is available here without
    anyone remembering to register it. That is the whole point: a hand-kept list of hand-kept
    lists is the same bug one level up.
    """
    found: dict[str, frozenset[str]] = {
        "DEVELOPMENT_RECORD_TYPES": frozenset(DEVELOPMENT_RECORD_TYPES),
        "SAFETY_RECORD_TYPES": frozenset(SAFETY_RECORD_TYPES),
        "SAFETY_SOURCE_SYSTEMS": frozenset(SAFETY_SOURCE_SYSTEMS),
        "SOURCE_ROLES": frozenset(SOURCE_ROLES),
        "FINDING_ROLES": frozenset(FINDING_ROLES),
        "INDICATOR_SPATIAL_TYPES": frozenset(INDICATOR_SPATIAL_TYPES),
        "ENTITY_TYPES": frozenset(ENTITY_TYPES),
        "EVIDENCE_CLASSES": frozenset(EVIDENCE_CLASSES),
        "EVIDENCE_DOMAINS": frozenset(EVIDENCE_DOMAINS),
    }
    for name in dir(scout_models):
        if not name.isupper():
            continue
        value = getattr(scout_models, name)
        if isinstance(value, (frozenset, set, tuple, list)) and value:
            if all(isinstance(item, str) for item in value):
                found[name] = frozenset(value)
    return found


def schema_literals() -> list[tuple[str, frozenset[str]]]:
    """Each `Literal[...]` in the schema, as a field name and its value set."""
    source = SCHEMA.read_text()
    out: list[tuple[str, frozenset[str]]] = []
    for match in re.finditer(r"(\w+):\s*Literal\[([^\]]+)\]", source, re.S):
        values = frozenset(re.findall(r'"([^"]+)"', match.group(2)))
        if values:
            out.append((match.group(1), values))
    return out


#: Literals the API owns, and why each has no domain vocabulary behind it.
#:
#: Keyed by the value set rather than the field name, because several fields share a name.
#: Each entry is a statement that this vocabulary belongs to the response shape rather than to
#: the domain, so a domain value cannot be missing from it.
API_OWNED: dict[frozenset[str], str] = {
    frozenset({"applicable", "not_applicable"}): (
        "whether a lane applied to an intent, decided by the controller at plan time"
    ),
    frozenset({"complete", "failed", "skipped"}): (
        "the outcome of one retrieval request, set by the searcher pipeline"
    ),
    frozenset({"<", "<=", "=", ">", ">="}): "comparison operators, not a vocabulary",
    frozenset({", "}): "a separator caught by the pattern, not a vocabulary",
    frozenset({"insufficient", "limited", "sufficient"}): (
        "how much a comparator cohort can carry, computed by the conformity stage"
    ),
    frozenset({"canonical", "title_fallback", "url_fallback"}): (
        "how a source was fingerprinted, decided by `_source_record_identity`"
    ),
    frozenset({"optimal", "other", "threshold"}): (
        "a target's role, read from the document by the target resolver"
    ),
    frozenset({"dynamic", "fixed"}): "whether a field's definition came from the document",
    frozenset({"evidence_review", "final", "target_review"}): (
        "which checkpoint a saved result is at, owned by the result envelope"
    ),
    frozenset({"measurements_found", "no_relevant_measurement", "not_assessed", "uncertain"}): (
        "the outcome of one target's measurement search"
    ),
    frozenset(
        {
            "specified",
            "not_present",
            "placeholder",
            "insufficient",
            "vague",
            "section_conflict",
            "not_applicable",
        }
    ): (
        # One entry, where there were three. A finding reason, a finding level and a
        # unit status all named the same judgement, and this file listing all three as
        # separate vocabularies is what made that look deliberate.
        "Inspector's verdicts, declared in its own service"
    ),
    frozenset({"complete", "failed", "not_applicable", "partial", "unknown"}): (
        "Inspector's cross-section consistency status"
    ),
    frozenset({"complete", "unknown"}): "Inspector's assessment status",
    frozenset({"answered", "not_applicable", "not_found", "partly_answered"}): (
        "Screener's answer states, declared in its own service"
    ),
    frozenset({"context", "document"}): "where Screener read an answer from",
    frozenset({"meets", "exceeds", "falls_short", "not_comparable", "not_addressed"}): (
        "Aligner's verdicts, declared in its own service"
    ),
}


class SchemaVocabularyTests(unittest.TestCase):
    def test_every_literal_matches_a_domain_vocabulary_or_is_declared_api_owned(self):
        domain = domain_vocabularies()
        unexplained: list[str] = []
        for field, values in schema_literals():
            if any(values == vocabulary for vocabulary in domain.values()):
                continue
            if values in API_OWNED:
                continue
            near = [
                f"{name} (missing {sorted(vocabulary - values)})"
                for name, vocabulary in domain.items()
                if values < vocabulary
            ]
            unexplained.append(
                f"{field}={sorted(values)}"
                + (f" -- looks like {near[0]}" if near else "")
            )
        self.assertEqual(
            unexplained,
            [],
            "a schema Literal matches no domain vocabulary and is not declared API-owned",
        )

    def test_the_record_type_that_started_this_is_complete(self):
        """The specific regression, asserted by name so it cannot come back quietly."""
        literals = dict(schema_literals())
        self.assertIn("record_type", literals)
        development = [
            values for field, values in schema_literals()
            if field == "record_type" and "clinical_trial" in values
        ]
        self.assertEqual(len(development), 1)
        self.assertEqual(development[0], frozenset(DEVELOPMENT_RECORD_TYPES))
        self.assertIn("announcement", development[0])

    def test_no_api_owned_entry_is_stale(self):
        """An allowlisted set that a domain vocabulary now covers should stop being allowlisted.

        Otherwise the allowlist becomes the place drift hides: a vocabulary moves into the
        domain and its schema copy keeps its exemption.
        """
        domain = domain_vocabularies()
        redundant = [
            sorted(values)
            for values in API_OWNED
            if any(values == vocabulary for vocabulary in domain.values())
        ]
        self.assertEqual(
            redundant, [], "this set now has a domain vocabulary; drop the exemption"
        )

    def test_every_api_owned_entry_states_a_reason(self):
        for values, reason in API_OWNED.items():
            self.assertGreater(len(reason), 20, sorted(values))

    def test_the_disposition_vocabulary_is_named_rather_than_written_out_twice(self):
        """It was inline in the model and again in the schema, with no name joining them."""
        self.assertEqual(
            scout_models.QUANTITATIVE_STATEMENT_DISPOSITIONS,
            frozenset({"context_only", "non_scalar", "range_or_set", "uncertain"}),
        )
        self.assertLess(
            scout_models.QUANTITATIVE_STATEMENT_DISPOSITIONS,
            frozenset(scout_models.QUANTITATIVE_REVIEW_CLASSIFICATIONS),
            "a disposition is a classification that is not a target",
        )
        self.assertNotIn(
            '"context_only",\n            "non_scalar"',
            pathlib.Path("services/scout/models.py").read_text(),
            "the disposition set is written out inline again",
        )


if __name__ == "__main__":
    unittest.main()
