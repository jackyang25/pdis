"""The directly called lanes: what each asks its provider, and what it makes of the answer.

Every lane here calls its provider through `calls.provider_request`, so one fake transport
stands in for all of them: it answers each provider with the shape that provider actually
returns (checked live when each lane was written) and records what was sent, so a test can
check the request a provider sees as well as the findings a lane builds.
"""

from __future__ import annotations

import json
import threading
import time
import unittest
import urllib.parse
from unittest.mock import patch

import services.searcher.calls as search_calls
import services.searcher.sources.semantic_scholar as semantic_scholar_source
from services.searcher import (
    RetrievalEntity,
    RetrievalError,
    RetrievalIntent,
    SafetyObservationRecord,
    SearchRequest,
    SearchRuntime,
    SourceQueryIntent,
    findings_to_dicts,
    plan_requests,
    run_requests,
    unconfigured_source_keys,
)

ISRCTN_XML = """<allTrials totalCount="2" xmlns="http://www.67bricks.com/isrctn">
<fullTrial>
  <trial>
    <isrctn dateAssigned="2025-07-02T08:24:19.210336Z">20573724</isrctn>
    <trialDescription>
      <title>A malaria vaccine challenge study</title>
      <scientificTitle>An open label phase I/IIa trial</scientificTitle>
      <primaryOutcomes/>
      <primaryOutcome>Solicited local adverse events</primaryOutcome>
    </trialDescription>
    <externalRefs><doi>10.1186/ISRCTN20573724</doi><eudraCTNumber/><clinicalTrialsGovNumber>NCT01234567</clinicalTrialsGovNumber></externalRefs>
    <trialDesign><studyDesign>Interventional non randomized</studyDesign></trialDesign>
    <participants>
      <recruitmentCountries><country>United Kingdom</country></recruitmentCountries>
      <targetEnrolment>35</targetEnrolment>
    </participants>
    <conditions><condition><description>Malaria</description></condition></conditions>
    <interventions><intervention>
      <interventionType>Biological/Vaccine</interventionType>
      <phase>Phase I/II</phase>
      <drugNames>R78C, RH5.1, Vaccine</drugNames>
    </intervention></interventions>
  </trial>
  <sponsor><organisation>University of Oxford</organisation></sponsor>
</fullTrial>
<fullTrial>
  <trial>
    <isrctn dateAssigned="2024-01-10T00:00:00Z">12416717</isrctn>
    <trialDescription>
      <title>Unfavourable outcome trial</title>
      <primaryOutcomes><outcomeMeasure>
        <variable>Unfavourable treatment outcome</variable>
        <timepoints>6 months</timepoints>
      </outcomeMeasure></primaryOutcomes>
    </trialDescription>
  </trial>
</fullTrial>
</allTrials>"""

OPENFDA_NOT_FOUND = RetrievalError("FDA", "http_error", "No matches found!", status=404)


def _answer(url: str, body: dict | None) -> object:
    """What each provider answers, keyed by the address it is asked at."""
    path = urllib.parse.urlsplit(url).path
    query = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
    if "europepmc" in url:
        return {"hitCount": 1, "resultList": {"result": [{
            "id": "41000001", "source": "MED", "pmid": "41000001", "pmcid": "PMC9000001",
            "doi": "10.1000/epmc", "title": "Malaria vaccine efficacy in children",
            "abstractText": "The vaccine reduced clinical malaria by 75%.",
            "firstPublicationDate": "2025-03-04", "pubYear": "2025",
        }]}}
    if "semanticscholar" in url:
        return {"total": 1, "data": [{
            "paperId": "abc123", "title": "A malaria vaccine study",
            "abstract": "The candidate reduced clinical malaria.",
            "year": 2024, "publicationDate": None,
            "externalIds": {"DOI": "10.1000/example", "PubMed": "39000001", "PubMedCentral": "123"},
        }]}
    if "isrctn" in url:
        return ISRCTN_XML.encode("utf-8")
    if "ctis-public-api" in url:
        return {"pagination": {"totalRecords": 1}, "data": [{
            "ctNumber": "2024-500001-11-00", "ctStatus": 8,
            "ctTitle": "Malaria vaccine efficacy study", "conditions": "Malaria",
            "trialPhase": "Phase 2", "trialCountries": ["Spain:8"], "product": "",
        }]}
    if path == "/drug/label.json" and "warnings" not in query.get("search", "") and "indications_and_usage" in query.get("search", ""):
        return {"results": [{
            "id": "00000000-0000-0000-0000-000000000001",
            "set_id": "00000000-0000-0000-0000-0000000000a1",
            "effective_time": "20240115",
            "indications_and_usage": ["Prevention of malaria."],
            "openfda": {"brand_name": ["Example vaccine"], "generic_name": ["malaria vaccine"],
                        "manufacturer_name": ["Example Co"]},
        }]}
    if path == "/drug/label.json":
        return {"results": [{
            "id": "00000000-0000-0000-0000-0000000000b1",
            "set_id": "00000000-0000-0000-0000-0000000000a1",
            # The current label format: warnings under `warnings_and_cautions`.
            "warnings_and_cautions": ["5.1 QT prolongation."],
            "openfda": {"brand_name": ["Example drug"]},
        }]}
    if path == "/device/510k.json":
        return {"results": [{
            "k_number": "K260001", "device_name": "Malaria diagnostic assay",
            "decision_date": "2026-07-01", "decision_description": "Substantially Equivalent",
        }]}
    if path == "/drug/event.json":
        return {"results": [{"term": "NAUSEA", "count": 12}]}
    if path == "/device/event.json":
        return {"results": [{
            "report_number": "MDR-1", "event_type": "Injury", "date_received": "20250102",
            "device": [{"generic_name": "Example assay"}],
        }]}
    if path == "/device/recall.json":
        return {"results": [{
            "product_res_number": "RES-1", "product_description": "Example assay",
            "recall_status": "Open", "classification": "Class II",
        }]}
    if "chembl" in url:
        return {"molecules": [{
            "molecule_chembl_id": "CHEMBL76", "pref_name": "CHLOROQUINE",
            "molecule_type": "Small molecule", "max_phase": "4.0", "first_approval": 1949,
        }]}
    if "opentargets" in url:
        variables = body["variables"]
        if "entity" in variables:
            hits = {
                "disease": [{"id": "MONDO_0005136", "name": "malaria"}],
                "target": [
                    {"id": "ENSG00000000001", "name": "CSPG4"},
                    {"id": "ENSG00000123456", "name": "CSP"},
                ],
            }[variables["entity"]]
            return {"data": {"search": {"hits": hits}}}
        return {"data": {"disease": {"id": "MONDO_0005136", "name": "malaria", "evidences": {"rows": [{
            "id": "row-1", "datasourceId": "europepmc", "datatypeId": "literature", "score": 0.72,
            "target": {"id": "ENSG00000123456", "approvedSymbol": "CSP"},
            "literature": ["12345678"], "urls": [],
        }]}}}}
    if "iris.who.int" in url:
        return {"_embedded": {"searchResult": {"page": {"totalElements": 1}, "_embedded": {"objects": [{
            "_embedded": {"indexableObject": {
                "handle": "10665/381003",
                "name": "WHO guidelines for malaria",
                "metadata": {
                    "dc.title": [{"value": "WHO guidelines for malaria"}],
                    "dc.date.issued": [{"value": "2025-04-04"}],
                    "dc.identifier.uri": [{"value": "https://iris.who.int/handle/10665/381003"}],
                    "dc.description.abstract": [{"value": "WHO recommends the RTS,S vaccine."}],
                },
            }},
        }]}}}}
    raise AssertionError(f"unexpected provider address: {url}")


class _Providers:
    """A fake transport: answers every provider and records what each was sent."""

    def __init__(self, failures: dict[str, Exception] | None = None):
        self.sent: list[dict] = []
        self.failures = failures or {}
        self.lock = threading.Lock()

    def fetch(self, url, *, provider, data=None, headers=None, method=None, **_):
        body = json.loads(data) if data else None
        with self.lock:
            self.sent.append({"url": url, "body": body, "headers": dict(headers or {}), "method": method})
        for marker, failure in self.failures.items():
            if marker in url:
                raise failure
        answer = _answer(url, body)
        return answer if isinstance(answer, bytes) else json.dumps(answer).encode("utf-8")

    def queries(self, marker: str) -> list[dict[str, str]]:
        return [
            dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(item["url"]).query))
            for item in self.sent
            if marker in item["url"]
        ]


class _NoopLLM:
    def search_web(self, query: str, *, max_tokens: int):
        raise AssertionError("web search should not run")


def _intent(**overrides) -> RetrievalIntent:
    fields = dict(
        scope_ref="efficacy",
        topic="clinical efficacy",
        description="Protective efficacy target",
        indication="malaria",
        intervention_class="vaccine",
        queries=(
            SourceQueryIntent(
                text="malaria vaccine efficacy trial",
                tracks=("general",),
                document_refs=("document/b-0001",),
            ),
        ),
    )
    fields.update(overrides)
    return RetrievalIntent(**fields)


def _run(sources, intent=None, *, credentials=None, providers=None):
    providers = providers or _Providers()
    runtime = SearchRuntime(
        llm_client=_NoopLLM(),
        credentials={"semantic_scholar": "s2-key", **(credentials or {})},
    )
    requests = plan_requests([intent or _intent()], sources=sources)
    with patch.object(search_calls, "fetch", providers.fetch), patch.object(search_calls, "pace"):
        outcomes = run_requests(requests, runtime=runtime, max_tokens=100)
    return requests, outcomes, providers


def _findings(outcomes):
    return [finding for outcome in outcomes for finding in outcome.findings]


class LiteratureLaneTests(unittest.TestCase):
    def test_europe_pmc_asks_for_core_records_bounded_by_its_own_date_field(self) -> None:
        _, outcomes, providers = _run(("europepmc",), _intent(published_since="2024-01-01"))

        query = providers.queries("europepmc")[0]
        self.assertEqual(query["resultType"], "core")
        self.assertEqual(query["pageSize"], "10")
        self.assertTrue(query["query"].endswith("AND FIRST_PDATE:[2024-01-01 TO 3000-12-31]"))
        finding = _findings(outcomes)[0]
        self.assertEqual(finding.record_key, "europepmc:MED/41000001")
        self.assertEqual(finding.url, "https://doi.org/10.1000/epmc")
        self.assertEqual(finding.identifiers["pmcid"], "PMC9000001")
        self.assertEqual((finding.published_at.isoformat()[:10], finding.published_precision), ("2025-03-04", "day"))
        self.assertEqual(finding.excerpt, "The vaccine reduced clinical malaria by 75%.")

    def test_semantic_scholar_sends_its_key_as_a_header_and_never_in_the_question(self) -> None:
        requests, outcomes, providers = _run(("semantic_scholar",), _intent(published_since="2023-06-01"))

        sent = next(item for item in providers.sent if "semanticscholar" in item["url"])
        self.assertEqual(sent["headers"]["x-api-key"], "s2-key")
        self.assertNotIn("s2-key", sent["url"])
        query = providers.queries("semanticscholar")[0]
        self.assertEqual(query["publicationDateOrYear"], "2023-06-01:")
        self.assertIn("abstract", query["fields"])
        self.assertEqual(requests[0].connector, "")
        finding = _findings(outcomes)[0]
        self.assertEqual(finding.record_key, "semantic_scholar:abc123")
        self.assertEqual(finding.url, "https://doi.org/10.1000/example")
        # Its own PubMed identifiers, so the paper merges with PubMed's and Europe PMC's copy.
        self.assertEqual(finding.identifiers, {"doi": "10.1000/example", "pmid": "39000001", "pmcid": "PMC123"})
        self.assertEqual(finding.published_precision, "year")
        self.assertEqual(finding.excerpt_kind, "passage")
        attribution = findings_to_dicts([finding])[0]["source_attributions"]["semantic_scholar"]
        self.assertEqual(attribution["url"], "https://www.semanticscholar.org/?utm_source=api")

    def test_semantic_scholar_is_unconfigured_without_its_key(self) -> None:
        """Keyless calls share a public pool that answered a live check with 429 at once."""
        self.assertEqual(
            unconfigured_source_keys(("semantic_scholar", "europepmc"), SearchRuntime(llm_client=None)),
            ("semantic_scholar",),
        )
        self.assertEqual(
            unconfigured_source_keys(
                ("semantic_scholar",),
                SearchRuntime(llm_client=None, credentials={"semantic_scholar": "key"}),
            ),
            (),
        )

    def test_semantic_scholar_paces_below_one_request_per_second(self) -> None:
        group = semantic_scholar_source.SEMANTIC_SCHOLAR
        previous = search_calls._NEXT_START.pop(group, None)
        try:
            with (
                patch("services.searcher.calls.time.monotonic", side_effect=(10.0, 10.5)),
                patch("services.searcher.calls.time.sleep") as sleep,
            ):
                search_calls.pace(group, semantic_scholar_source.MIN_REQUEST_INTERVAL_SECONDS)
                search_calls.pace(group, semantic_scholar_source.MIN_REQUEST_INTERVAL_SECONDS)
        finally:
            search_calls._NEXT_START.pop(group, None)
            if previous is not None:
                search_calls._NEXT_START[group] = previous
        sleep.assert_called_once()
        self.assertGreaterEqual(sleep.call_args.args[0], 0.59)
        self.assertGreater(semantic_scholar_source.MIN_REQUEST_INTERVAL_SECONDS, 1.0)

    def test_who_searches_only_who_guidelines_and_reads_their_abstracts(self) -> None:
        _, outcomes, providers = _run(("who_guidelines",), _intent(published_since="2022-01-01"))

        self.assertEqual(len(providers.sent), 1, "a guideline needs no second call")
        query = providers.queries("iris.who.int")[0]
        self.assertEqual(query["f.subject"], "WHO guideline,equals")
        self.assertEqual(query["f.language"], "en,equals")
        self.assertEqual(query["f.dateIssued"], "[2022-01-01 TO *],equals")
        self.assertEqual(query["query"], "malaria")
        finding = _findings(outcomes)[0]
        self.assertEqual(finding.record_key, "who_guidelines:10665/381003")
        self.assertEqual(finding.url, "https://iris.who.int/handle/10665/381003")
        self.assertEqual(finding.excerpt, "WHO recommends the RTS,S vaccine.")
        self.assertEqual(finding.evidence_role, "evidence")


class RegistryLaneTests(unittest.TestCase):
    def test_registries_preserve_the_complete_neutral_intent_bundle(self) -> None:
        queries = (
            SourceQueryIntent(text="malaria vaccine efficacy trial", tracks=("general",),
                              document_refs=("document/b-0001",)),
            SourceQueryIntent(text="malaria vaccine efficacy limitation", tracks=("counterfactual",),
                              document_refs=("document/b-0002",)),
        )
        requests = plan_requests([_intent(queries=queries)], sources=("ctis", "isrctn", "fda"))

        self.assertEqual(len(requests), 3)
        for request in requests:
            self.assertEqual(request.intent_ids, tuple(query.intent_id for query in queries))
            self.assertEqual(request.input_queries, tuple(query.text for query in queries))
            self.assertEqual(request.document_refs, ("document/b-0001", "document/b-0002"))
            self.assertEqual(request.tracks, ("general", "counterfactual"))

    def test_isrctn_reads_both_outcome_forms_and_dates_a_trial_by_registration(self) -> None:
        _, outcomes, providers = _run(("isrctn",), _intent(region="Kenya"))

        sent = [query["q"] for query in providers.queries("isrctn")]
        self.assertEqual(sent, [
            "condition:malaria AND intervention:vaccine",
            "condition:malaria AND intervention:vaccine AND recruitmentCountry:Kenya",
        ])
        first, second = _findings(outcomes)[:2]
        self.assertEqual(first.record_key, "isrctn:ISRCTN20573724")
        self.assertEqual(first.identifiers["nct"], "NCT01234567")
        self.assertEqual(first.published_at.isoformat()[:10], "2025-07-02")
        self.assertIn("Primary outcomes: Solicited local adverse events", first.excerpt)
        self.assertIn("Primary outcomes: Unfavourable treatment outcome - 6 months", second.excerpt)
        # As the registry states it: a comma is not a programme boundary ("RTS,S").
        self.assertEqual([record.program_name for record in first.development_records], ["R78C, RH5.1, Vaccine"])
        self.assertEqual(first.development_records[0].sponsor, "University of Oxford")

    def test_ctis_posts_one_condition_search_and_names_the_status_code(self) -> None:
        requests, outcomes, providers = _run(("ctis",))

        sent = next(item for item in providers.sent if "ctis" in item["url"])
        self.assertEqual(sent["method"], "POST")
        self.assertEqual(sent["body"], {
            "pagination": {"page": 1, "size": 10},
            "searchCriteria": {"medicalCondition": "malaria"},
        })
        finding = _findings(outcomes)[0]
        self.assertEqual(finding.record_key, "ctis:2024-500001-11-00")
        self.assertIn("Status: Ended", finding.excerpt)
        self.assertIsNone(finding.published_at)


class OpenFDALaneTests(unittest.TestCase):
    def test_labels_are_harmonized_records_dated_by_their_version(self) -> None:
        requests, outcomes, providers = _run(("fda",), credentials={"openfda": "fda-key"})

        query = providers.queries("api.fda.gov")[0]
        self.assertEqual(query["search"], 'indications_and_usage:"malaria" AND _exists_:openfda.generic_name')
        self.assertEqual(query["api_key"], "fda-key")
        self.assertEqual(requests[0].operation, "drug/label")
        finding = _findings(outcomes)[0]
        self.assertEqual(finding.title, "Example vaccine (malaria vaccine)")
        self.assertEqual(finding.identifiers["setid"], "00000000-0000-0000-0000-0000000000a1")
        self.assertEqual(finding.published_at.isoformat()[:10], "2024-01-15")
        self.assertEqual(finding.development_records[0].sponsor, "Example Co")
        self.assertNotIn("fda-key", finding.url)

    def test_a_device_class_asks_the_510k_endpoint_without_a_scout_branch(self) -> None:
        requests, outcomes, _ = _run(("fda",), _intent(intervention_class="diagnostic"))

        self.assertEqual(requests[0].operation, "device/510k")
        self.assertEqual(
            _findings(outcomes)[0].url,
            "https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpmn/pmn.cfm?ID=K260001",
        )

    def test_nothing_matched_is_an_empty_answer_not_a_failure(self) -> None:
        providers = _Providers(failures={"api.fda.gov": OPENFDA_NOT_FOUND})
        _, outcomes, _ = _run(("fda",), providers=providers)

        self.assertEqual(outcomes[0].status, "complete")
        self.assertEqual(outcomes[0].findings, [])

    def test_safety_keeps_label_warnings_and_noncausal_report_counts_apart(self) -> None:
        intent = _intent(
            scope_ref="safety", intervention_class="drug", evidence_domain="safety",
            queries=(SourceQueryIntent(text="CAB-LA safety reports"),),
            entities=(RetrievalEntity("CAB-LA", "drug"),),
        )
        requests, outcomes, providers = _run(("fda_safety",), intent)

        self.assertEqual([request.operation for request in requests], ["label_warnings", "reported_events"])
        counts = next(query for query in providers.queries("drug/event.json"))
        self.assertEqual(counts["count"], "patient.reaction.reactionmeddrapt.exact")
        findings = _findings(outcomes)
        warning = next(f for f in findings if f.safety_observations[0].record_type == "label_warning")
        reported = next(f for f in findings if f.safety_observations[0].record_type == "reported_event")
        # A current-format label's warnings, which the old field list never read.
        self.assertIn("QT prolongation", warning.excerpt)
        self.assertEqual(warning.evidence_role, "evidence")
        self.assertEqual(reported.evidence_role, "reference")
        self.assertEqual(reported.safety_observations[0].report_count, 12)
        self.assertIn("do not establish", reported.safety_observations[0].qualification)
        # The query whose total is the count shown, so the count can be checked.
        search = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(reported.url).query))["search"]
        self.assertEqual(
            search,
            f'({requests[1].query}) AND patient.reaction.reactionmeddrapt.exact:"NAUSEA"',
        )
        self.assertEqual(reported.record_key, "fda_safety:faers:CAB-LA:NAUSEA")

    def test_safety_reads_device_events_and_recalls_separately(self) -> None:
        intent = _intent(
            scope_ref="safety", intervention_class="diagnostic", evidence_domain="safety",
            queries=(SourceQueryIntent(text="malaria assay safety"),),
            entities=(RetrievalEntity("Example assay", "device"),),
        )
        _, outcomes, _ = _run(("fda_safety",), intent)

        observations = [record for finding in _findings(outcomes) for record in finding.safety_observations]
        self.assertEqual(
            {(record.record_type, record.source_system) for record in observations},
            {("device_event", "maude"), ("recall", "fda_recall")},
        )
        self.assertTrue(all(record.report_count is None for record in observations))

    def test_safety_observation_contract_rejects_invalid_source_counts(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown safety source system"):
            SafetyObservationRecord(product_name="Example drug", record_type="reported_event",
                                    source_system="unknown_source", label="Nausea", report_count=12)
        with self.assertRaisesRegex(ValueError, "FAERS report count is required"):
            SafetyObservationRecord(product_name="Example drug", record_type="reported_event",
                                    source_system="faers", label="Nausea")
        with self.assertRaisesRegex(ValueError, "only FAERS observations"):
            SafetyObservationRecord(product_name="Example device", record_type="recall",
                                    source_system="fda_recall", label="Class II", report_count=1)
        with self.assertRaisesRegex(ValueError, "cannot be negative"):
            SafetyObservationRecord(product_name="Example drug", record_type="reported_event",
                                    source_system="faers", label="Nausea", report_count=-1)


class MolecularLaneTests(unittest.TestCase):
    def _intent(self, *entities: RetrievalEntity) -> RetrievalIntent:
        return _intent(
            scope_ref="mechanism", intervention_class="drug", evidence_domain="biological",
            queries=(SourceQueryIntent(text="malaria chloroquine circumsporozoite protein"),),
            entities=entities,
        )

    def test_open_targets_and_chembl_normalize_their_own_records(self) -> None:
        _, outcomes, providers = _run(
            ("open_targets", "chembl"),
            self._intent(RetrievalEntity("chloroquine", "drug"), RetrievalEntity("CSP", "protein")),
        )

        self.assertTrue(all(outcome.status == "complete" for outcome in outcomes))
        findings = _findings(outcomes)
        open_targets = next(f for f in findings if f.source == "open_targets")
        self.assertEqual(open_targets.record_key, "open_targets:row-1")
        self.assertEqual(open_targets.url, "https://europepmc.org/article/MED/12345678")
        self.assertEqual(open_targets.evidence_role, "evidence")
        evidence = next(item for item in providers.sent if "opentargets" in item["url"]
                        and "target" in item["body"]["variables"])
        # The hit whose symbol is the stated name, not the one the search ranked first.
        self.assertEqual(evidence["body"]["variables"]["target"], "ENSG00000123456")
        chembl = next(f for f in findings if f.source == "chembl")
        self.assertEqual(chembl.url, "https://www.ebi.ac.uk/chembl/explore/compound/CHEMBL76")
        self.assertEqual(chembl.evidence_role, "reference")
        self.assertEqual(chembl.development_records[0].phase, "Phase 4")
        self.assertEqual(providers.queries("chembl")[0]["q"], "chloroquine")

    def test_a_target_name_that_is_no_symbol_gets_no_evidence(self) -> None:
        """Open Targets indexes human genes: a pathogen protein would resolve to whichever
        gene its search ranked first, and that gene's evidence would read as this one's."""
        _, outcomes, providers = _run(
            ("open_targets",), self._intent(RetrievalEntity("circumsporozoite protein", "protein"))
        )

        self.assertEqual(outcomes[0].status, "complete")
        self.assertEqual(outcomes[0].findings, [])
        self.assertFalse(any("target" in item["body"]["variables"] for item in providers.sent))

    def test_a_refused_graphql_query_is_a_rejected_failure(self) -> None:
        class Refusing(_Providers):
            def fetch(self, url, **kwargs):
                return json.dumps({"errors": [{"message": "Cannot query field"}]}).encode()

        _, outcomes, _ = _run(
            ("open_targets",), self._intent(RetrievalEntity("CSP", "protein")), providers=Refusing()
        )

        self.assertEqual(outcomes[0].status, "failed")
        self.assertEqual(outcomes[0].error_code, "rejected")
        self.assertIn("Cannot query field", outcomes[0].error)


class ProviderRequestTests(unittest.TestCase):
    def test_a_key_is_sent_but_never_part_of_the_memo_or_an_error(self) -> None:
        from services.searcher.sources.fda import FDASource
        from services.searcher.sources.openfda import openfda_search

        sent: list[dict] = []

        def answering(url, **kwargs):
            sent.append({"url": url, "secrets": kwargs["secrets"]})
            return json.dumps({"results": []}).encode()

        runtime = SearchRuntime(llm_client=None, credentials={"openfda": "secret"})
        with patch.object(search_calls, "fetch", answering), patch.object(search_calls, "pace"):
            openfda_search(runtime, FDASource.spec, "drug/label.json", "x", limit=1)
        self.assertIn("api_key=secret", sent[0]["url"])
        # Handed to the transport to strip from any error body that echoes it.
        self.assertEqual(sent[0]["secrets"], ("secret",))
        self.assertNotIn("secret", repr(list(runtime.calls._cache._entries)))
        self.assertNotIn("secret", repr(runtime))

    def test_identical_calls_in_one_run_reach_the_provider_once(self) -> None:
        intents = [
            _intent(scope_ref=f"field-{index}", queries=(SourceQueryIntent(text=f"query {index}"),))
            for index in range(3)
        ]
        providers = _Providers()
        runtime = SearchRuntime(llm_client=_NoopLLM())
        requests = plan_requests(intents, sources=("ctis",))
        with patch.object(search_calls, "fetch", providers.fetch), patch.object(search_calls, "pace"):
            outcomes = run_requests(requests, runtime=runtime, max_tokens=100)

        self.assertEqual(len(providers.sent), 1)
        self.assertEqual([len(outcome.findings) for outcome in outcomes], [1, 1, 1])


class SchedulingTests(unittest.TestCase):
    """The controller's fan-out, exercised through a directly called lane."""

    def _requests(self, count: int) -> list[SearchRequest]:
        return plan_requests(
            [
                _intent(scope_ref=f"field-{index}", queries=(SourceQueryIntent(text=f"query {index}"),))
                for index in range(count)
            ],
            sources=("europepmc",),
        )

    def test_global_worker_limit_bounds_source_fanout(self) -> None:
        state = {"active": 0, "max": 0}
        lock = threading.Lock()

        def slow(url, **kwargs):
            with lock:
                state["active"] += 1
                state["max"] = max(state["max"], state["active"])
            time.sleep(0.01)
            with lock:
                state["active"] -= 1
            return json.dumps({"resultList": {"result": []}}).encode()

        runtime = SearchRuntime(llm_client=_NoopLLM(), global_worker_limit=2)
        with patch.object(search_calls, "fetch", slow), patch.object(search_calls, "pace"):
            run_requests(self._requests(8), runtime=runtime, max_tokens=100)

        self.assertEqual(state["max"], 2)

    def test_progress_counter_survives_multiple_scheduler_waves(self) -> None:
        updates: list[tuple[int, int]] = []
        runtime = SearchRuntime(llm_client=_NoopLLM(), global_worker_limit=1)
        with patch.object(search_calls, "fetch", _Providers().fetch), patch.object(search_calls, "pace"):
            outcomes = run_requests(
                self._requests(2), runtime=runtime, max_tokens=100,
                progress=lambda completed, total: updates.append((completed, total)),
            )

        self.assertEqual(len(outcomes), 2)
        self.assertEqual(updates, [(0, 2), (1, 2), (2, 2)])

    def test_slow_lane_does_not_occupy_fast_lane_worker(self) -> None:
        web_started = threading.Event()
        observed: list[bool] = []

        class CoordinatedLLM:
            def search_web(self, query: str, *, max_tokens: int):
                web_started.set()
                return {"output": []}

        def waiting(url, **kwargs):
            observed.append(web_started.wait(timeout=0.5))
            return json.dumps({"resultList": {"result": []}}).encode()

        requests = [
            SearchRequest(scope_ref=f"field-{index}", source="europepmc", query=f"paper query {index}")
            for index in range(4)
        ]
        requests.append(SearchRequest(scope_ref="field-web", source="web", query="web query"))
        runtime = SearchRuntime(llm_client=CoordinatedLLM(), global_worker_limit=2)
        with patch.object(search_calls, "fetch", waiting), patch.object(search_calls, "pace"):
            outcomes = run_requests(requests, runtime=runtime, max_tokens=100)

        self.assertTrue(observed and observed[0])
        self.assertEqual([outcome.request for outcome in outcomes], requests)

    def test_an_inapplicable_lane_makes_no_call(self) -> None:
        query = SourceQueryIntent(text="chloroquine target mechanism", tracks=("general",),
                                  document_refs=("document/b-0004",))
        intent = _intent(
            scope_ref="mechanism", intervention_class="drug", queries=(query,),
            evidence_domain="biological",
            entities=(RetrievalEntity("chloroquine", "drug"), RetrievalEntity("CSP", "protein")),
        )
        requests = plan_requests([intent], sources=("clinicaltrials", "fda", "open_targets", "chembl"))
        by_source = {request.source: request for request in requests}

        self.assertEqual(by_source["open_targets"].applicability, "applicable")
        self.assertEqual(by_source["chembl"].applicability, "applicable")
        for source in ("clinicaltrials", "fda"):
            skipped = by_source[source]
            self.assertEqual(skipped.applicability, "not_applicable")
            self.assertEqual(skipped.intent_ids, (query.intent_id,))
            self.assertEqual(skipped.document_refs, ("document/b-0004",))
            self.assertTrue(skipped.applicability_reason)

        providers = _Providers()
        with patch.object(search_calls, "fetch", providers.fetch):
            outcomes = run_requests([by_source["fda"]], runtime=SearchRuntime(llm_client=_NoopLLM()),
                                    max_tokens=100)
        self.assertEqual(outcomes[0].status, "skipped")
        self.assertEqual(providers.sent, [])


if __name__ == "__main__":
    unittest.main()
