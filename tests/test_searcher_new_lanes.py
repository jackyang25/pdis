"""The two lanes added to close declared gaps, and what each one is for.

Europe PMC is a third literature lane and not a redundant one: it indexes what PubMed
does and adds preprints from bioRxiv and medRxiv plus open-access full text. A trial
result reaches a preprint server before a journal, so a set of lanes that sees only
journals sees the competitive landscape late.

WHO Guidelines is the only lane in the `guidance` class, and it is the closest thing the
ToolUniverse catalogue exposes to an LMIC authority: a regulator states what is permitted
in its own market, while WHO states what should be done, and that is what ministries and
procurement bodies follow where no national regulator has ruled.

Neither lane was chosen for being easy. EMA, WHO ICTRP, Gavi and conference abstracts were
all looked for and are not in the catalogue, which is why `MISSING_COVERAGE` and
`MISSING_JURISDICTIONS` still name what they name.
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

    def test_it_reads_only_what_its_tool_accepts(self) -> None:
        """The tool takes one topic, so declaring more would claim a narrowing it
        cannot apply."""
        self.assertEqual(sorted(_spec("who_guidelines").reads), ["condition", "text"])

    def test_it_asks_about_the_condition(self) -> None:
        (request,) = plan_requests([_intent()], sources=("who_guidelines",))
        self.assertEqual(dict(request.options)["condition"], "malaria")
        self.assertEqual(request.query, "condition:malaria")

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

    The search tool returns `content` and `description` as null, so the first version of
    this lane produced findings with zero-length excerpts. It declared that it feeds
    insights while giving the model a title to reason from - the same shape as the lane
    that fed nothing at all, just harder to see.
    """

    class _Connector:
        def __init__(self, *, fail_text: bool = False) -> None:
            self.fail_text = fail_text
            self.calls: list[str] = []

        def run(self, tool, arguments):
            self.calls.append(tool)
            if tool == "WHO_Guidelines_Search":
                return [
                    {
                        "title": "Guiding principles for malaria",
                        "url": "https://www.who.int/publications/i/item/B09790",
                        "description": None,
                        "content": None,
                        "is_guideline": True,
                    },
                    {"title": "A publication list", "url": "https://www.who.int/x", "is_guideline": False},
                ]
            if self.fail_text:
                raise RuntimeError("page would not load")
            return {"main_content": "WHO recommends seasonal chemoprevention.", "overview": ""}

    def _search(self, connector):
        from services.searcher import SearchRuntime
        from services.searcher.sources.who_guidelines import WHOGuidelinesSource

        source = WHOGuidelinesSource()
        (request,) = source.plan(_intent())
        return source.search(
            request,
            SearchRuntime(llm_client=None, integrations={"tooluniverse": connector}),
            max_tokens=100,
            max_uses=1,
        )

    def test_a_guideline_carries_its_page_text(self) -> None:
        connector = self._Connector()
        (finding,) = self._search(connector)
        self.assertEqual(finding.excerpt, "WHO recommends seasonal chemoprevention.")
        self.assertIn("WHO_Guideline_Full_Text", connector.calls)

    def test_a_page_that_will_not_load_degrades_the_finding_not_the_lane(self) -> None:
        """The guideline exists and is citable either way; losing the whole request
        because one page failed would be a worse answer than a thin one."""
        (finding,) = self._search(self._Connector(fail_text=True))
        self.assertIsNone(finding.excerpt)
        self.assertTrue(finding.url)

    def test_a_publication_list_is_not_a_guideline(self) -> None:
        """The class is an authority's position, and a list of publications is not one."""
        findings = self._search(self._Connector())
        self.assertEqual([f.url for f in findings], ["https://www.who.int/publications/i/item/B09790"])

    def test_the_result_cap_is_small_because_each_result_costs_a_second_call(self) -> None:
        from services.searcher.sources.who_guidelines import MAX_RESULTS

        self.assertLessEqual(MAX_RESULTS, 5)

    def test_the_full_text_tool_is_allowlisted(self) -> None:
        """Its operations drive the connector allowlist, so an unlisted tool is refused."""
        self.assertIn("WHO_Guideline_Full_Text", _spec("who_guidelines").operations)


class LaneBalanceTests(unittest.TestCase):
    def test_literature_is_no_longer_the_thinnest_class(self) -> None:
        """Why Europe PMC was added and openalex was not: a fourth literature lane would
        have deepened the best-served class while regulatory stayed at one country."""
        counts: dict[str, int] = {}
        for spec in source_specs():
            counts[spec.evidence_class] = counts.get(spec.evidence_class, 0) + 1
        self.assertEqual(counts["literature"], 3)
        self.assertGreaterEqual(counts["literature"], counts["molecular"])

    def test_every_new_lane_is_off_by_default(self) -> None:
        """Both need the ToolUniverse connector, so enabling them by default would make
        an unconfigured deployment report two failed lanes on every run."""
        for key in ("europepmc", "who_guidelines"):
            with self.subTest(lane=key):
                self.assertFalse(_spec(key).default_enabled)
                self.assertTrue(_spec(key).integration_key)


if __name__ == "__main__":
    unittest.main()
