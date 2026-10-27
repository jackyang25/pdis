"""A finding's identity is the record's, stated by the provider, never its page or title."""

from __future__ import annotations

import json
import unittest
import urllib.parse
from datetime import date, datetime, timezone
from unittest.mock import patch

import services.searcher.calls as search_calls

from services.searcher import (
    Finding,
    RetrievalEntity,
    RetrievalIntent,
    SearchRequest,
    SearchRuntime,
    SourceQueryIntent,
    dedupe_findings,
    plan_requests,
    run_requests,
    source_specs,
)
from services.searcher.sources.chembl import ChEMBLSource, _phase_label
from services.searcher.sources.ctis import CTISSource
from services.searcher.sources.europepmc import EuropePMCSource
from services.searcher.sources.fda import FDASource
from services.searcher.sources.fda_safety import FDASafetySource
from services.searcher.sources.isrctn import ISRCTNSource
from services.searcher.sources.records import structured_excerpt
from services.searcher.stages.clinicaltrials import clinicaltrial_to_finding

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


class _Provider:
    """A fake transport: each call is answered by the first address fragment it contains."""

    def __init__(self, answers: dict[str, object]):
        self.answers = answers
        self.sent: list[tuple[str, dict]] = []

    def fetch(self, url, *, data=None, **_):
        parameters = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
        self.sent.append((url, json.loads(data) if data else parameters))
        answer = next(value for fragment, value in self.answers.items() if fragment in url)
        return answer if isinstance(answer, bytes) else json.dumps(answer).encode("utf-8")

    def search(self, adapter, request):
        with patch.object(search_calls, "fetch", self.fetch), patch.object(search_calls, "pace"):
            return adapter.search(request, SearchRuntime(llm_client=None), max_tokens=1)

    def run(self, requests):
        with patch.object(search_calls, "fetch", self.fetch), patch.object(search_calls, "pace"):
            return run_requests(requests, runtime=SearchRuntime(llm_client=None), max_tokens=1)


def _finding(**kwargs) -> Finding:
    values = {"url": "https://example.test/a", "title": "A", "query": "q", "retrieved_at": NOW}
    values.update(kwargs)
    return Finding(**values)


def _safety_intent() -> RetrievalIntent:
    return RetrievalIntent(
        scope_ref="safety",
        topic="safety",
        description="",
        indication="malaria",
        intervention_class="drug",
        queries=(SourceQueryIntent(text="chloroquine safety"),),
        evidence_domain="safety",
        entities=(RetrievalEntity("chloroquine", "drug"),),
    )


class DistinctRecordsStayDistinctTests(unittest.TestCase):
    def test_two_faers_reactions_are_two_records(self) -> None:
        """They shared a URL told apart by a fragment, which canonical URLs drop."""
        provider = _Provider(
            {
                "drug/label.json": {"results": []},
                "drug/event.json": {"results": [
                    {"term": "NAUSEA", "count": 12},
                    {"term": "HEADACHE", "count": 7},
                ]},
            }
        )
        outcomes = provider.run(plan_requests([_safety_intent()], sources=("fda_safety",)))
        findings = dedupe_findings(f for outcome in outcomes for f in outcome.findings)

        self.assertEqual(
            sorted(f.safety_observations[0].label for f in findings), ["Headache", "Nausea"]
        )
        self.assertEqual(len({f.url for f in findings}), 2)

    def test_a_label_warning_without_a_set_id_is_not_kept(self) -> None:
        provider = _Provider(
            {
                "drug/label.json": {
                    "results": [
                        {"openfda": {"brand_name": ["A"]}, "warnings": ["Warning one."]},
                        {
                            "openfda": {"brand_name": ["B"]},
                            "set_id": "00000000-0000-0000-0000-0000000000a1",
                            "warnings": ["Warning two."],
                        },
                    ]
                },
            }
        )
        request = SearchRequest(
            scope_ref="safety",
            source="fda_safety",
            query='openfda.brand_name:"chloroquine"',
            operation="label_warnings",
            options=(("product_name", "chloroquine"),),
        )
        findings = provider.search(FDASafetySource(), request)

        self.assertEqual(len(findings), 1)
        self.assertEqual(
            findings[0].url,
            "https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?"
            "setid=00000000-0000-0000-0000-0000000000a1",
        )
        self.assertEqual(
            findings[0].identifiers, {"setid": "00000000-0000-0000-0000-0000000000a1"}
        )

    def test_a_drug_label_is_addressed_by_its_own_document_id(self) -> None:
        """`id` is a version id; DailyMed's `setid` answers it with nothing."""
        spl_id = "5431bb85-f36f-4286-9597-9ff0049588d8"
        provider = _Provider(
            {
                "drug/label.json": {
                    "results": [
                        {"openfda": {"brand_name": ["No id"]}, "indications_and_usage": ["Malaria."]},
                        {"openfda": {"brand_name": ["Doxy"]}, "id": spl_id,
                         "indications_and_usage": ["Malaria."]},
                    ]
                }
            }
        )
        request = plan_requests(
            [
                RetrievalIntent(
                    scope_ref="q",
                    topic="malaria",
                    description="",
                    indication="malaria",
                    intervention_class="drug",
                    queries=(SourceQueryIntent(text="malaria drug"),),
                )
            ],
            sources=("fda",),
        )[0]
        findings = provider.search(FDASource(), request)

        self.assertEqual(len(findings), 1)
        self.assertEqual(
            findings[0].url,
            "https://api.fda.gov/drug/label.json?search=id%3A%22" + spl_id + "%22",
        )
        self.assertEqual(findings[0].record_key, f"fda:label:{spl_id}")

    def test_a_registry_placeholder_is_not_an_identifier(self) -> None:
        """"Nil known" read as a trial number would make every such record one record."""
        trial = (
            "<fullTrial><trial><isrctn>{}</isrctn><externalRefs>"
            "<clinicalTrialsGovNumber>Nil known</clinicalTrialsGovNumber></externalRefs>"
            "</trial></fullTrial>"
        )
        provider = _Provider(
            {
                "isrctn": (
                    '<allTrials xmlns="http://www.67bricks.com/isrctn">'
                    + trial.format("11111111") + trial.format("22222222") + "</allTrials>"
                ).encode()
            }
        )
        request = SearchRequest(scope_ref="q", source="isrctn", query="condition:malaria")
        findings = provider.search(ISRCTNSource(), request)

        self.assertEqual([f.identifiers for f in findings], [
            {"isrctn": "ISRCTN11111111"}, {"isrctn": "ISRCTN22222222"},
        ])
        self.assertEqual(len(dedupe_findings(findings)), 2)


class OneRecordAcrossLanesTests(unittest.TestCase):
    def test_one_paper_from_two_lanes_is_one_finding_with_both_lanes(self) -> None:
        pubmed = _finding(
            url="https://pubmed.ncbi.nlm.nih.gov/123/",
            source="pubmed",
            query="pubmed query",
            identifiers={"pmid": "123", "doi": "10.1000/ABC"},
            record_key="pubmed:123",
            excerpt="Abstract.",
        )
        europe = _finding(
            url="https://doi.org/10.1000/abc",
            source="europepmc",
            query="europe query",
            identifiers={"doi": "https://doi.org/10.1000/abc"},
            record_key="europepmc:MED/123",
            excerpt="A longer abstract text.",
        )

        (merged,) = dedupe_findings([pubmed, europe])

        self.assertEqual(merged.source_lanes, ["pubmed", "europepmc"])
        self.assertEqual(
            {(path.lane, path.query) for path in merged.retrieval_paths},
            {("pubmed", "pubmed query"), ("europepmc", "europe query")},
        )
        self.assertEqual(merged.identifiers, {"pmid": "123", "doi": "10.1000/abc"})

    def test_a_record_bridging_two_held_records_merges_all_three(self) -> None:
        a = _finding(url="https://a.test", source="pubmed", record_key="pubmed:1",
                     identifiers={"pmid": "1"})
        b = _finding(url="https://b.test", source="europepmc", record_key="europepmc:x",
                     identifiers={"doi": "10.1000/x"})
        bridge = _finding(url="https://c.test", source="semantic_scholar",
                          record_key="semantic_scholar:s",
                          identifiers={"doi": "10.1000/x", "pmid": "1"})

        self.assertEqual(len(dedupe_findings([a, b, bridge])), 1)

    def test_lane_scoped_identifiers_do_not_merge_lanes(self) -> None:
        """An FDA label and its warnings share a set id but carry different content."""
        label = _finding(source="fda", record_key="fda:label:x",
                         identifiers={"setid": "00000000-0000-0000-0000-000000000001"})
        warnings = _finding(url="https://example.test/b", source="fda_safety",
                            record_key="fda_safety:label_warning:x",
                            identifiers={"setid": "00000000-0000-0000-0000-000000000001"})
        self.assertEqual(len(dedupe_findings([label, warnings])), 2)

    def test_a_page_cited_by_the_web_joins_the_record_on_that_page(self) -> None:
        trial = _finding(url="https://clinicaltrials.gov/study/NCT00000001",
                         source="clinicaltrials", record_key="clinicaltrials:NCT00000001")
        web = _finding(url="https://clinicaltrials.gov/study/NCT00000001", source="web")
        self.assertEqual(len(dedupe_findings([trial, web])), 1)

    def test_an_unknown_scheme_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            _finding(identifiers={"isbn": "123"})


class TitlesAreTitlesTests(unittest.TestCase):
    def test_pubmed_titles_carry_no_identifier(self) -> None:
        from services.searcher.stages import pubmed

        root = pubmed.ET.fromstring(
            "<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>42</PMID><Article>"
            "<Journal><Title>J</Title><JournalIssue><PubDate><Year>2024</Year>"
            "<Month>Mar</Month></PubDate></JournalIssue></Journal>"
            "<ArticleTitle>A <i>study</i></ArticleTitle></Article></MedlineCitation>"
            "<PubmedData><ArticleIdList><ArticleId IdType=\"doi\">10.1/x</ArticleId>"
            "<ArticleId IdType=\"pmc\">PMC9</ArticleId></ArticleIdList></PubmedData>"
            "</PubmedArticle></PubmedArticleSet>"
        )
        with patch.object(pubmed, "_request_xml", return_value=root):
            (record,) = pubmed._efetch_pubmed(SearchRuntime(llm_client=None), ["42"])

        self.assertEqual(record["title"], "A study - J")
        self.assertEqual((record["doi"], record["pmcid"]), ("10.1/x", "PMC9"))
        self.assertEqual(record["published_precision"], "month")


class ProviderOrderTests(unittest.TestCase):
    """A request asks for what it keeps, and keeps it in the provider's order."""

    def test_every_structured_lane_asks_for_its_declared_count(self) -> None:
        for adapter, request, answer, count in (
            (CTISSource(), SearchRequest(scope_ref="q", source="ctis", query="x",
                                         options=(("medical_condition", "malaria"),)),
             {"data": []}, lambda sent: sent["pagination"]["size"]),
            (ISRCTNSource(), SearchRequest(scope_ref="q", source="isrctn", query="condition:malaria"),
             b'<allTrials xmlns="http://www.67bricks.com/isrctn"/>', lambda sent: sent["limit"]),
            (EuropePMCSource(), SearchRequest(scope_ref="q", source="europepmc", query="x"),
             {"resultList": {"result": []}}, lambda sent: sent["pageSize"]),
            (ChEMBLSource(), SearchRequest(scope_ref="q", source="chembl", query="x",
                                           options=(("entity_name", "chloroquine"),)),
             {"molecules": []}, lambda sent: sent["limit"]),
        ):
            with self.subTest(lane=adapter.spec.key):
                provider = _Provider({"": answer})
                provider.search(adapter, request)
                ((_, sent),) = provider.sent
                self.assertEqual(int(count(sent)), adapter.spec.max_results)

    def test_records_keep_the_providers_order(self) -> None:
        provider = _Provider(
            {
                "ctis": {
                    "data": [
                        {"ctNumber": "2024-500001-11-00", "ctTitle": "Unrelated"},
                        {"ctNumber": "2024-500002-11-00", "ctTitle": "Malaria vaccine efficacy"},
                    ]
                }
            }
        )
        request = SearchRequest(
            scope_ref="q", source="ctis", query="medical_condition:malaria",
            input_queries=("malaria vaccine efficacy",),
            options=(("medical_condition", "malaria"),),
        )
        findings = provider.search(CTISSource(), request)
        self.assertEqual([f.title for f in findings], ["Unrelated", "Malaria vaccine efficacy"])

    def test_a_records_excerpt_does_not_depend_on_who_asked(self) -> None:
        record = {"phase": "Phase 3", "conditions": ["Malaria"], "sponsor": "Org"}
        fields = (("conditions", "Conditions"), ("phase", "Phase"), ("sponsor", "Sponsor"))
        self.assertEqual(
            structured_excerpt(record, fields), "Conditions: Malaria\nPhase: Phase 3\nSponsor: Org"
        )

    def test_no_lane_carries_an_unused_ranking_option(self) -> None:
        intent = RetrievalIntent(
            scope_ref="q", topic="malaria", description="", indication="malaria",
            intervention_class="vaccine", queries=(SourceQueryIntent(text="malaria vaccine"),),
        )
        keys = [spec.key for spec in source_specs() if not spec.required_entity_types]
        for request in plan_requests([intent], sources=keys):
            self.assertNotIn("ranking", dict(request.options))
            self.assertNotIn("candidate_limit", dict(request.options))


class RegistryDatesTests(unittest.TestCase):
    def test_a_trial_is_dated_by_when_it_was_first_posted(self) -> None:
        finding = clinicaltrial_to_finding(
            {
                "protocolSection": {
                    "identificationModule": {"nctId": "NCT00000001", "briefTitle": "T"},
                    "statusModule": {
                        "studyFirstPostDateStruct": {"date": "2012-03"},
                        "lastUpdatePostDateStruct": {"date": "2025-11-02"},
                    },
                }
            },
            "q",
        )
        self.assertEqual(finding.published_at.date(), date(2012, 3, 1))
        self.assertEqual(finding.published_precision, "month")
        self.assertEqual(finding.identifiers, {"nct": "NCT00000001"})
        self.assertTrue(finding.published_before(date(2013, 1, 1)))
        self.assertFalse(finding.published_before(date(2012, 3, 15)))

    def test_ctis_states_no_publication_date(self) -> None:
        """Its search returns only the latest edit and the EU start, neither a publication."""
        provider = _Provider(
            {"ctis": {"data": [{"ctNumber": "2024-500001-11-00", "lastUpdated": "01/07/2026",
                                "startDateEU": "05/04/2024"}]}}
        )
        request = SearchRequest(scope_ref="q", source="ctis", query="x",
                                options=(("medical_condition", "malaria"),))
        (finding,) = provider.search(CTISSource(), request)
        self.assertIsNone(finding.published_at)
        self.assertEqual(finding.identifiers, {"euct": "2024-500001-11-00"})


class PartialDateTests(unittest.TestCase):
    def test_a_year_is_before_a_bound_only_if_all_of_it_is(self) -> None:
        finding = _finding(
            published_at=datetime(2024, 1, 1, tzinfo=timezone.utc), published_precision="year"
        )
        self.assertFalse(finding.published_before(date(2024, 6, 1)))
        self.assertTrue(finding.published_before(date(2025, 1, 1)))

    def test_no_date_is_never_before_anything(self) -> None:
        self.assertFalse(_finding().published_before(date(2999, 1, 1)))

    def test_europe_pmc_keeps_a_bare_year_as_a_year(self) -> None:
        provider = _Provider(
            {
                "europepmc": {
                    "resultList": {"result": [
                        {"title": "A", "source": "MED", "id": "1", "pmid": "1", "pubYear": "2024"},
                        {"title": "B", "source": "MED", "id": "2",
                         "firstPublicationDate": "2024-09-30", "pubYear": "2024"},
                    ]}
                }
            }
        )
        request = SearchRequest(scope_ref="q", source="europepmc", query="x")
        a, b = provider.search(EuropePMCSource(), request)
        self.assertEqual((a.published_precision, b.published_precision), ("year", "day"))
        self.assertEqual(a.record_key, "europepmc:MED/1")
        self.assertEqual(a.url, "https://europepmc.org/article/MED/1")

    def test_a_europe_pmc_answer_without_a_result_list_is_a_failure(self) -> None:
        """An answer missing its list is not one that matched nothing."""
        provider = _Provider({"europepmc": {"errCode": 500, "errMsg": "temporarily unavailable"}})
        request = SearchRequest(scope_ref="q", source="europepmc", query="x")
        with self.assertRaisesRegex(RuntimeError, "no result list"):
            provider.search(EuropePMCSource(), request)


class ChEMBLTests(unittest.TestCase):
    def test_an_unknown_phase_is_not_preclinical(self) -> None:
        self.assertEqual(_phase_label(-1), "")
        self.assertEqual(_phase_label(None), "")
        self.assertEqual(_phase_label(0.5), "Early Phase 1")
        self.assertEqual(_phase_label("4"), "Phase 4")

    def test_targets_are_not_searched_because_nothing_reads_them(self) -> None:
        self.assertNotIn("protein", ChEMBLSource.spec.required_entity_types)
        self.assertNotIn("gene", ChEMBLSource.spec.required_entity_types)


if __name__ == "__main__":
    unittest.main()
