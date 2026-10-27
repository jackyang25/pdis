"""The two lanes added to close declared gaps, and what each one is for.

Europe PMC is a third literature lane and not a redundant one: it indexes what PubMed
does and adds preprints from bioRxiv and medRxiv plus open-access full text. A trial
result reaches a preprint server before a journal, so a set of lanes that sees only
journals sees the competitive landscape late.

WHO Guidelines is the only lane in the `guidance` class, and the closest this service has
to an LMIC authority: a regulator states what is permitted in its own market, while WHO
states what should be done, and that is what ministries and procurement bodies follow where
no national regulator has ruled.

EMA, WHO ICTRP, Gavi and conference abstracts publish no search API a lane could call, which
is why `MISSING_COVERAGE` and `MISSING_JURISDICTIONS` still name what they name.
"""

from __future__ import annotations

import unittest

from services.searcher import (
    RetrievalIntent,
    SourceQueryIntent,
    plan_requests,
    source_specs,
)
from services.searcher.sources.europepmc import _bounded


def _intent(**overrides) -> RetrievalIntent:
    fields = dict(
        scope_ref="q",
        topic="efficacy",
        description="",
        indication="malaria",
        intervention_class="vaccine",
        queries=(SourceQueryIntent(text="malaria vaccine efficacy", tracks=("general",)),),
    )
    fields.update(overrides)
    return RetrievalIntent(**fields)


def _spec(key: str):
    return next(spec for spec in source_specs() if spec.key == key)


class EuropePMCTests(unittest.TestCase):
    def test_it_is_a_literature_lane_that_bounds_at_the_provider(self) -> None:
        spec = _spec("europepmc")
        self.assertEqual(spec.evidence_class, "literature")
        self.assertTrue(spec.honors_date_bound)

    def test_a_window_becomes_the_providers_date_field(self) -> None:
        """Not a term. `2026` alone matches records mentioning it; the field matches
        records published then. Verified against live results before wiring."""
        bounded = _bounded("malaria vaccine efficacy", "2026-01-01")
        self.assertIn("FIRST_PDATE:[2026-01-01 TO", bounded)
        self.assertTrue(bounded.startswith("malaria vaccine efficacy"))

    def test_no_window_leaves_the_query_untouched(self) -> None:
        self.assertEqual(_bounded("malaria efficacy", ""), "malaria efficacy")

    def test_it_plans_one_request_per_track(self) -> None:
        intent = _intent(
            queries=(
                SourceQueryIntent(text="efficacy", tracks=("general",)),
                SourceQueryIntent(text="waning", tracks=("counterfactual",)),
            )
        )
        requests = plan_requests([intent], sources=("europepmc",))
        self.assertEqual({r.tracks for r in requests}, {("general",), ("counterfactual",)})

    def test_the_window_reaches_the_request(self) -> None:
        (request,) = plan_requests(
            [_intent(published_since="2026-01-01")], sources=("europepmc",)
        )
        self.assertEqual(dict(request.options)["published_since"], "2026-01-01")


class WHOGuidelinesTests(unittest.TestCase):
    def test_it_is_the_only_guidance_lane(self) -> None:
        guidance = [s.key for s in source_specs() if s.evidence_class == "guidance"]
        self.assertEqual(guidance, ["who_guidelines"])

    def test_guidance_is_separate_from_regulatory(self) -> None:
        """The test that justifies a class of its own: sources in one class are
        alternatives, and a WHO recommendation does not answer what a label permits."""
        self.assertNotEqual(
            _spec("who_guidelines").evidence_class, _spec("fda").evidence_class
        )

    def test_it_reads_only_what_its_search_accepts(self) -> None:
        """The search takes one topic, so declaring more would claim a narrowing it
        cannot apply."""
        self.assertEqual(sorted(_spec("who_guidelines").reads), ["condition", "text"])

    def test_it_asks_about_the_condition(self) -> None:
        (request,) = plan_requests([_intent()], sources=("who_guidelines",))
        self.assertEqual(request.query, "malaria")

    def test_its_findings_are_evidence_not_reference(self) -> None:
        """An earlier draft marked them `reference` by analogy to a press release, and
        the analogy was wrong: a guideline is an independent authority's published text,
        not an interested party's claim about its own product. The coverage test caught
        it, because a `reference`-only lane cannot declare that it feeds insights."""
        import pathlib

        source = pathlib.Path("services/searcher/sources/who_guidelines.py").read_text()
        self.assertNotIn('evidence_role="reference"', source)
        self.assertIn("insights", _spec("who_guidelines").feeds)


class WHOGuidelinesTextTests(unittest.TestCase):
    """A finding with no text is a title, and a title is not a passage.

    The lane once scraped WHO's site, whose links carried no text, and fell back to WHO's
    list of recent guidelines when a condition had no topic page - guidance on any subject,
    filed under this one. IRIS states both what a record is and what it says.
    """

    def _search(self, objects):
        import json
        from unittest.mock import patch

        import services.searcher.calls as search_calls
        from services.searcher import SearchRuntime
        from services.searcher.sources.who_guidelines import WHOGuidelinesSource

        sent: list[str] = []

        def fetch(url, **kwargs):
            sent.append(url)
            return json.dumps({"_embedded": {"searchResult": {
                "page": {"totalElements": len(objects)},
                "_embedded": {"objects": [{"_embedded": {"indexableObject": item}} for item in objects]},
            }}}).encode()

        source = WHOGuidelinesSource()
        (request,) = source.plan(_intent())
        with patch.object(search_calls, "fetch", fetch), patch.object(search_calls, "pace"):
            return source.search(request, SearchRuntime(llm_client=None), max_tokens=100), sent

    def _item(self, handle: str, **metadata):
        return {"handle": handle, "metadata": {key: [{"value": value}] for key, value in metadata.items()}}

    def test_a_guideline_carries_whos_own_summary(self) -> None:
        (finding,), sent = self._search([self._item(
            "10665/1", **{"dc.title": "Guidelines for malaria",
                          "dc.description.abstract": "WHO recommends seasonal chemoprevention."},
        )])
        self.assertEqual(finding.excerpt, "WHO recommends seasonal chemoprevention.")
        self.assertEqual(len(sent), 1)

    def test_a_guideline_without_a_summary_is_kept_as_a_citable_title(self) -> None:
        """The guideline exists and is citable either way; dropping it would be a worse
        answer than a thin one."""
        (finding,), _ = self._search([self._item("10665/2", **{"dc.title": "Guidelines"})])
        self.assertIsNone(finding.excerpt)
        self.assertEqual(finding.url, "https://iris.who.int/handle/10665/2")

    def test_only_records_who_tags_as_guidelines_are_asked_for(self) -> None:
        """The class is an authority's position, and IRIS's own tag says which records are."""
        _, sent = self._search([])
        self.assertIn("f.subject=WHO+guideline%2Cequals", sent[0])

    def test_the_result_cap_stays_a_curated_handful(self) -> None:
        from services.searcher.sources.who_guidelines import MAX_RESULTS

        self.assertLessEqual(MAX_RESULTS, 5)


class LaneBalanceTests(unittest.TestCase):
    def test_literature_is_no_longer_the_thinnest_class(self) -> None:
        """Why Europe PMC was added and openalex was not: a fourth literature lane would
        have deepened the best-served class while regulatory stayed at one country."""
        counts: dict[str, int] = {}
        for spec in source_specs():
            counts[spec.evidence_class] = counts.get(spec.evidence_class, 0) + 1
        self.assertEqual(counts["literature"], 3)
        self.assertGreaterEqual(counts["literature"], counts["molecular"])

    def test_a_lane_is_off_by_default_only_when_it_needs_a_named_entity(self) -> None:
        """Off by default once meant "needs the ToolUniverse connector". Every lane is now
        called directly, so the one remaining reason is a lane that plans nothing until a
        caller names a product or a target."""
        for spec in source_specs():
            with self.subTest(lane=spec.key):
                self.assertEqual(spec.default_enabled, not spec.required_entity_types)


if __name__ == "__main__":
    unittest.main()
