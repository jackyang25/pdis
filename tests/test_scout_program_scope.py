"""Questions about the run, not about one variable.

Every query Scout sends belongs to a document variable, and every finding is filed under
one. "Has anything been announced about this program" belongs to no variable: the answer
is the same whether you asked it while reading efficacy or cold chain. Filing it under a
variable would be a lie, and a track asking it per variable would ask twenty times.

So it gets its own scope key. Nothing else changes, and that is the claim these tests
hold:

    the key needs no new structure   `findings_by_attribute` is keyed by `scope_ref`
    it cannot reach per-variable reasoning   insight extraction excludes it, and the
                                             result assembly would refuse it anyway
    it reaches the landscape for free   that projection groups by program, not variable
    it does not read as a variable      the label layer names it for what it is
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from services.scout.models import (
    PROGRAM_QUERY_SETS,
    PROGRAM_SCOPE_KEY,
    Attribute,
    RetrievalScopeLedger,
)
from services.scout.stages.intent_builder import (
    build_program_intents,
    build_retrieval_intents,
)
from services.searcher import source_keys


def _ledger(**overrides) -> RetrievalScopeLedger:
    supplied = {
        "condition": ("melanoma", "header"),
        "intervention": ("vaccine", "header"),
    }
    supplied.update(overrides)
    return RetrievalScopeLedger.of(**supplied)


class DeclarationTests(unittest.TestCase):
    def test_every_set_targets_registered_lanes(self) -> None:
        registered = set(source_keys())
        for name, query_set in PROGRAM_QUERY_SETS.items():
            with self.subTest(query_set=name):
                self.assertTrue(query_set.lanes)
                self.assertEqual(sorted(set(query_set.lanes) - registered), [])

    def test_every_set_states_why_only_those_lanes(self) -> None:
        """A lane list with no reason is a lane list nobody can review."""
        for name, query_set in PROGRAM_QUERY_SETS.items():
            with self.subTest(query_set=name):
                self.assertGreater(len(query_set.reason.split()), 8)

    def test_no_subject_asks_for_recency_instead_of_naming_an_event(self) -> None:
        """The same rule the query extractor is held to, for the same reason.

        An index reads "recent" and "2026" as terms to match, so a query asking for
        newness narrows to documents that happen to contain the word. An announcement is
        reached by naming the kind of event.
        """
        forbidden = ("recent", "latest", "new ", "current", "upcoming", "202")
        for name, query_set in PROGRAM_QUERY_SETS.items():
            for subject in query_set.subjects:
                with self.subTest(subject=subject):
                    for term in forbidden:
                        self.assertNotIn(term, subject.lower())


class IntentTests(unittest.TestCase):
    def test_intents_carry_the_program_scope_and_their_lanes(self) -> None:
        built = build_program_intents(_ledger())
        self.assertEqual(len(built), len(PROGRAM_QUERY_SETS))
        for intent, lanes in built:
            self.assertEqual(intent.scope_ref, PROGRAM_SCOPE_KEY)
            self.assertTrue(lanes)

    def _set(self, name: str, **ledger):
        """One named set's intent. Named rather than unpacked, since there are several."""
        built = build_program_intents(_ledger(**ledger.pop("scope", {})), **ledger)
        return next(intent for intent, _ in built if intent.topic == name)

    def test_the_run_scope_reaches_the_query_text(self) -> None:
        """The web lane reads only text, so scope absent from the text is scope lost."""
        intent = self._set("events")
        for query in intent.queries:
            self.assertIn("melanoma", query.text)
            self.assertIn("vaccine", query.text)

    def test_a_set_with_no_subjects_still_carries_one_query(self) -> None:
        """A request with no query carries no lineage, so nothing can be traced back.

        Builds its own set rather than naming a real one. The burden set was the only
        subject-less member and it was removed with the WHO GHO lane, so a test naming it
        went with it - but the behaviour outlives the set that happened to need it, and
        the next subject-less set should not have to rediscover this.
        """
        from services.scout.models import ProgramQuerySet

        subjectless = {"probe": ProgramQuerySet(subjects=(), lanes=("web",), reason="test")}
        with patch.dict(PROGRAM_QUERY_SETS, subjectless, clear=True):
            intent = self._set("probe")
        self.assertEqual([q.text for q in intent.queries], ["melanoma vaccine"])

    def test_a_stated_region_is_carried(self) -> None:
        intent = self._set(
            "events", scope={"region": ("Kenya", "document", ("profile/b-0007",))}
        )
        self.assertEqual(intent.scope("region"), "Kenya")

    def test_no_condition_means_no_program_questions(self) -> None:
        """A bare event subject would return announcements from every field of medicine."""
        self.assertEqual(build_program_intents(RetrievalScopeLedger.of()), [])

    def test_the_window_is_carried_like_any_other_intent(self) -> None:
        intent = self._set("events", published_since="2026-01-01")
        self.assertEqual(intent.published_since, "2026-01-01")

    def test_the_program_scope_is_not_an_attribute_name(self) -> None:
        """Otherwise the key would collide with a variable and be filed as one."""
        from services.scout.models import QueryIntent

        attribute = Attribute(name="vaccine.efficacy", description="Efficacy.")
        (variable_intent,) = build_retrieval_intents(
            {"vaccine.efficacy": [QueryIntent(text="efficacy", tracks=["general"])]},
            [attribute],
            scope=_ledger(),
        )
        self.assertNotEqual(variable_intent.scope_ref, PROGRAM_SCOPE_KEY)


class SeamTests(unittest.TestCase):
    """The four claims the seam rests on, each checked against the code that carries it."""

    def test_findings_are_keyed_by_scope_ref_not_by_attribute(self) -> None:
        """So the key needs no new structure. Read from the source, not assumed."""
        import pathlib

        pipeline = (
            pathlib.Path(__file__).resolve().parents[1]
            / "services"
            / "scout"
            / "pipeline.py"
        ).read_text()
        self.assertIn("findings_by_attribute.setdefault(task.scope_ref", pipeline)

    def test_insight_extraction_excludes_the_program_scope(self) -> None:
        import pathlib

        pipeline = (
            pathlib.Path(__file__).resolve().parents[1]
            / "services"
            / "scout"
            / "pipeline.py"
        ).read_text()
        self.assertIn("if attribute_ref != PROGRAM_SCOPE_KEY", pipeline)

    def test_an_insight_naming_the_program_scope_would_be_refused(self) -> None:
        """The backstop behind that filter, so removing the filter fails loudly."""
        import pathlib

        pipeline = (
            pathlib.Path(__file__).resolve().parents[1]
            / "services"
            / "scout"
            / "pipeline.py"
        ).read_text()
        self.assertIn("references unknown field", pipeline)

    def test_the_landscape_groups_by_program_not_by_variable(self) -> None:
        """Which is why program findings reach it with no change at all."""
        from datetime import datetime, timezone

        from services.scout.projections import build_development_landscape
        from services.searcher import DevelopmentRecord, Finding

        record = DevelopmentRecord(
            program_name="V940",
            record_type="clinical_trial",
            record_id="NCT1",
            sponsor="Merck",
        )
        finding = Finding(
            url="https://example.org/a",
            title="a",
            query="q",
            retrieved_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            development_records=[record],
        )
        (program,) = build_development_landscape({PROGRAM_SCOPE_KEY: [finding]})
        self.assertEqual(program.name, "V940")
        self.assertEqual(program.attribute_refs, [PROGRAM_SCOPE_KEY])


if __name__ == "__main__":
    unittest.main()
