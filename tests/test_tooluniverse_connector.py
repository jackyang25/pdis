from __future__ import annotations

import json
import threading
import time
import unittest
from unittest.mock import patch

from api.deps import get_search_integrations
import services.searcher.controller as search_controller
import services.searcher.sources.semantic_scholar as semantic_scholar_source
from services.searcher import (
    RetrievalEntity,
    RetrievalIntent,
    SafetyObservationRecord,
    SearchRequest,
    SearchRuntime,
    SourceQueryIntent,
    ToolUniverseHTTPConnector,
    findings_to_dicts,
    integration_operations,
    plan_requests,
    run_requests,
    unconfigured_source_keys,
)


class _NoopLLM:
    def search_web(self, query: str, *, max_tokens: int, max_uses: int):
        raise AssertionError("web search should not run")


class _FakeToolUniverse:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def run(self, tool_name: str, arguments: dict):
        self.calls.append((tool_name, arguments))
        return {
            "status": "success",
            "data": [
                {
                    "title": "A malaria vaccine study",
                    "abstract": "The candidate reduced clinical malaria.",
                    "doi": "10.1000/example",
                    "doi_url": "https://doi.org/10.1000/example",
                }
            ],
        }


class _MultiSourceToolUniverse:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def run(self, tool_name: str, arguments: dict):
        self.calls.append((tool_name, arguments))
        if tool_name == "CTIS_search_trials_filtered":
            return {
                "status": "success",
                "data": [
                    {
                        "ct_number": "2024-500001-11-00",
                        "title": "Malaria vaccine efficacy study",
                        "conditions": ["Malaria"],
                        "phase": "Phase 2",
                        "last_updated": "01/07/2026",
                    }
                ],
            }
        if tool_name == "ISRCTN_search_trials_fielded":
            return {
                "status": "success",
                "data": [
                    {
                        "isrctn_id": "ISRCTN12345678",
                        "title": "Malaria vaccine trial",
                        "conditions": ["Malaria"],
                        "interventions": ["Vaccine"],
                    }
                ],
            }
        if tool_name == "FDA_search_drug_labels":
            return {
                "status": "success",
                "data": [
                    {
                        "brand_name": "Example vaccine",
                        "generic_name": "malaria vaccine",
                        "spl_id": "00000000-0000-0000-0000-000000000001",
                        "indications_and_usage": "Prevention of malaria.",
                    }
                ],
            }
        if tool_name == "OpenFDA_search_device_510k":
            return {
                "status": "success",
                "data": {
                    "meta": {"results": {"total": 1}},
                    "results": [
                        {
                            "k_number": "K260001",
                            "device_name": "Malaria diagnostic assay",
                            "decision_date": "2026-07-01",
                            "decision_description": "Substantially Equivalent",
                        }
                    ],
                },
            }
        if tool_name == "OpenTargets_get_evidence_by_datasource":
            return {
                "status": "success",
                "data": {
                    "disease": {
                        "id": "EFO_0001068",
                        "name": "Malaria",
                        "evidences": {
                            "rows": [
                            {
                                "datasourceId": "europepmc",
                                "datatypeId": "literature",
                                "score": 0.72,
                                "target": {
                                    "id": "ENSG00000123456",
                                    "approvedSymbol": "CSP",
                                },
                                "literature": ["12345678"],
                            }
                            ]
                        },
                    }
                },
            }
        if tool_name == "ChEMBL_search_drugs":
            return {
                "status": "success",
                "data": {
                    "molecules": [
                        {
                            "molecule_chembl_id": "CHEMBL76",
                            "pref_name": "CHLOROQUINE",
                            "molecule_type": "Small molecule",
                            "max_phase": 4,
                        }
                    ]
                },
            }
        if tool_name == "ChEMBL_search_targets":
            return {"status": "success", "data": {"targets": []}}
        if tool_name == "FDA_get_warnings_by_drug_name":
            return {
                "results": [
                    {
                        "openfda.brand_name": ["Example drug"],
                        "warnings": ["May cause severe hypersensitivity."],
                    }
                ]
            }
        if tool_name == "FAERS_count_reactions_by_drug_event":
            return [{"term": "NAUSEA", "count": 12}]
        if tool_name == "OpenFDA_search_device_adverse_events":
            return {
                "results": [
                    {
                        "report_number": "MDR-1",
                        "event_type": "Injury",
                        "device": [{"generic_name": "Example assay"}],
                    }
                ]
            }
        if tool_name == "OpenFDA_search_device_recalls":
            return {
                "results": [
                    {
                        "product_res_number": "RES-1",
                        "product_description": "Example assay",
                        "recall_status": "Open",
                        "classification": "Class II",
                    }
                ]
            }
        raise AssertionError(f"unexpected ToolUniverse operation: {tool_name}")


class _CountingToolUniverse:
    def __init__(self):
        self.active = 0
        self.max_active = 0
        self.lock = threading.Lock()

    def run(self, tool_name: str, arguments: dict):
        with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        time.sleep(0.01)
        with self.lock:
            self.active -= 1
        return {"status": "success", "data": []}


class _CoordinatedToolUniverse:
    def __init__(self, web_started: threading.Event):
        self.web_started = web_started
        self.observed_web_start = False

    def run(self, tool_name: str, arguments: dict):
        self.observed_web_start = self.web_started.wait(timeout=0.5)
        return {"status": "success", "data": []}


class _CoordinatedLLM:
    def __init__(self, web_started: threading.Event):
        self.web_started = web_started

    def search_web(self, query: str, *, max_tokens: int, max_uses: int):
        self.web_started.set()
        return {"output": []}


class _HTTPResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class ToolUniverseConnectorTests(unittest.TestCase):
    def test_semantic_scholar_throttle_stays_below_one_request_per_second(self) -> None:
        source = "semantic_scholar"
        previous = search_controller._NEXT_SOURCE_START.get(source)
        search_controller._NEXT_SOURCE_START.pop(source, None)
        try:
            with (
                patch(
                    "services.searcher.controller.time.monotonic",
                    side_effect=(10.0, 10.5),
                ),
                patch("services.searcher.controller.time.sleep") as sleep,
            ):
                search_controller._wait_for_source_start(
                    source,
                    semantic_scholar_source.MIN_REQUEST_INTERVAL_SECONDS,
                )
                search_controller._wait_for_source_start(
                    source,
                    semantic_scholar_source.MIN_REQUEST_INTERVAL_SECONDS,
                )
        finally:
            if previous is None:
                search_controller._NEXT_SOURCE_START.pop(source, None)
            else:
                search_controller._NEXT_SOURCE_START[source] = previous

        sleep.assert_called_once()
        self.assertGreaterEqual(sleep.call_args.args[0], 0.59)
        self.assertGreater(semantic_scholar_source.MIN_REQUEST_INTERVAL_SECONDS, 1.0)

    def test_the_connector_is_configured_from_one_address_variable(self) -> None:
        """A URL, and nothing to compose it from.

        A host and port pair said nothing this cannot, and two ways to state one
        address let a deployment set both and be wrong in a way neither value
        shows. Platforms that publish a private service as host and port compose
        them where the deployment is described - `jobspec.nomad` resolves the
        connector through service discovery and writes this variable.
        """
        with patch.dict(
            "os.environ",
            {
                "TOOLUNIVERSE_BASE_URL": "http://pdis-tooluniverse.internal:8080",
                "TOOLUNIVERSE_API_TOKEN": "generated-token",
            },
            clear=True,
        ):
            connector = get_search_integrations()["tooluniverse"]

        self.assertEqual(connector.base_url, "http://pdis-tooluniverse.internal:8080")
        self.assertEqual(connector.api_token, "generated-token")

    def test_no_connector_is_built_without_an_address(self) -> None:
        """Retrieval degrades to the direct-HTTP lanes rather than constructing a
        connector pointed at nothing. A host/port pair left over from an older
        deployment must not be enough to bring one back."""
        with patch.dict(
            "os.environ",
            {
                "TOOLUNIVERSE_HOST": "leftover.internal",
                "TOOLUNIVERSE_PORT": "8080",
            },
            clear=True,
        ):
            self.assertNotIn("tooluniverse", get_search_integrations())

    def test_http_connector_enforces_allowlist_and_contract(self) -> None:
        connector = ToolUniverseHTTPConnector(
            base_url="http://tooluniverse.test:8080",
            api_token="secret-token",
            allowed_tools=frozenset({"SemanticScholar_search_papers"}),
        )
        response = _HTTPResponse(
            {"success": True, "result": {"status": "success", "data": []}}
        )

        with patch(
            "services.searcher.connectors.tooluniverse.urlopen",
            return_value=response,
        ) as mocked:
            result = connector.run(
                "SemanticScholar_search_papers",
                {"query": "malaria vaccine", "limit": 5},
            )

        self.assertEqual(result["status"], "success")
        request = mocked.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["method"], "run_one_function")
        self.assertEqual(
            payload["kwargs"]["function_call_json"]["name"],
            "SemanticScholar_search_papers",
        )
        self.assertEqual(request.get_header("Authorization"), "Bearer secret-token")

        with self.assertRaisesRegex(ValueError, "not allowlisted"):
            connector.run("PythonExecutor", {"code": "pass"})

    def test_semantic_scholar_is_a_normal_traced_source_adapter(self) -> None:
        connector = _FakeToolUniverse()
        runtime = SearchRuntime(
            llm_client=_NoopLLM(),
            integrations={"tooluniverse": connector},
        )
        intent = RetrievalIntent(
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

        requests = plan_requests([intent], sources=("semantic_scholar",))
        with patch("services.searcher.controller._wait_for_source_start") as throttle:
            outcomes = run_requests(
                requests,
                runtime=runtime,
                max_tokens=100,
                max_uses=1,
            )

        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0].connector, "tooluniverse")
        self.assertEqual(requests[0].operation, "SemanticScholar_search_papers")
        self.assertEqual(outcomes[0].status, "complete")
        self.assertTrue(connector.calls[0][1]["include_abstract"])
        finding = outcomes[0].findings[0]
        self.assertEqual(finding.source, "semantic_scholar")
        self.assertEqual(finding.url, "https://doi.org/10.1000/example")
        self.assertEqual(finding.source_labels, {"semantic_scholar": "Semantic Scholar"})
        attribution = finding.source_attributions["semantic_scholar"]
        self.assertEqual(attribution.label, "Semantic Scholar")
        self.assertEqual(attribution.prefix, "Academic metadata provided by")
        serialized = findings_to_dicts([finding])[0]
        self.assertEqual(
            serialized["source_attributions"]["semantic_scholar"]["url"],
            "https://www.semanticscholar.org/?utm_source=api",
        )
        self.assertEqual(len(finding.retrieval_paths), 1)
        self.assertEqual(finding.retrieval_paths[0].connector, "tooluniverse")
        self.assertEqual(
            finding.retrieval_paths[0].operation,
            "SemanticScholar_search_papers",
        )
        self.assertEqual(
            integration_operations("tooluniverse"),
            (
                "CTIS_search_trials_filtered",
                "ISRCTN_search_trials_fielded",
                "SemanticScholar_search_papers",
                "EuropePMC_search_articles",
                "WHO_Guidelines_Search",
                "WHO_Guideline_Full_Text",
                "OpenTargets_get_evidence_by_datasource",
                "ChEMBL_search_drugs",
                "ChEMBL_search_targets",
                "FDA_search_drug_labels",
                "OpenFDA_search_device_510k",
                "FDA_get_warnings_by_drug_name",
                "FAERS_count_reactions_by_drug_event",
                "OpenFDA_search_device_adverse_events",
                "OpenFDA_search_device_recalls",
            ),
        )
        throttle.assert_called_once_with(
            "semantic_scholar",
            semantic_scholar_source.MIN_REQUEST_INTERVAL_SECONDS,
        )

    def test_missing_connector_is_detectable_before_execution(self) -> None:
        runtime = SearchRuntime(llm_client=_NoopLLM())

        self.assertEqual(
            unconfigured_source_keys(
                (
                    "web",
                    "ctis",
                    "isrctn",
                    "semantic_scholar",
                    "open_targets",
                    "chembl",
                    "fda",
                ),
                runtime,
            ),
            (
                "ctis",
                "isrctn",
                "semantic_scholar",
                "open_targets",
                "chembl",
                "fda",
            ),
        )

    def test_source_applicability_is_explicit_and_preserves_lineage(self) -> None:
        query = SourceQueryIntent(
            text="chloroquine target mechanism",
            tracks=("general",),
            document_refs=("document/b-0004",),
        )
        intent = RetrievalIntent(
            scope_ref="mechanism",
            topic="mechanism of action",
            description="Biological mechanism",
            indication="malaria",
            intervention_class="drug",
            queries=(query,),
            evidence_domain="biological",
            entities=(
                RetrievalEntity("chloroquine", "drug"),
                RetrievalEntity("CSP", "protein"),
            ),
        )

        requests = plan_requests(
            [intent],
            sources=("web", "clinicaltrials", "fda", "open_targets", "chembl"),
        )
        by_source: dict[str, list[SearchRequest]] = {}
        for request in requests:
            by_source.setdefault(request.source, []).append(request)

        self.assertEqual(by_source["web"][0].applicability, "applicable")
        self.assertEqual(by_source["open_targets"][0].applicability, "applicable")
        self.assertEqual(by_source["chembl"][0].applicability, "applicable")
        for source in ("clinicaltrials", "fda"):
            skipped = by_source[source][0]
            self.assertEqual(skipped.applicability, "not_applicable")
            self.assertEqual(skipped.intent_ids, (query.intent_id,))
            self.assertEqual(skipped.input_queries, (query.text,))
            self.assertEqual(skipped.document_refs, ("document/b-0004",))
            self.assertTrue(skipped.applicability_reason)

        connector = _MultiSourceToolUniverse()
        outcomes = run_requests(
            [by_source["clinicaltrials"][0]],
            runtime=SearchRuntime(
                llm_client=_NoopLLM(),
                integrations={"tooluniverse": connector},
            ),
            max_tokens=100,
            max_uses=1,
        )
        self.assertEqual(outcomes[0].status, "skipped")
        self.assertEqual(connector.calls, [])

    def test_biomedical_lanes_normalize_source_specific_records(self) -> None:
        connector = _MultiSourceToolUniverse()
        runtime = SearchRuntime(
            llm_client=_NoopLLM(),
            integrations={"tooluniverse": connector},
        )
        intent = RetrievalIntent(
            scope_ref="mechanism",
            topic="mechanism of action",
            description="Biological mechanism",
            indication="malaria",
            intervention_class="drug",
            queries=(
                SourceQueryIntent(
                    text="malaria chloroquine circumsporozoite protein",
                    tracks=("general",),
                    document_refs=("document/b-0004",),
                ),
            ),
            evidence_domain="biological",
            entities=(
                RetrievalEntity("chloroquine", "drug"),
                RetrievalEntity("circumsporozoite protein", "protein"),
            ),
        )
        requests = plan_requests(
            [intent],
            sources=("open_targets", "chembl"),
        )

        outcomes = run_requests(
            requests,
            runtime=runtime,
            max_tokens=100,
            max_uses=1,
        )
        findings = [
            finding
            for outcome in outcomes
            for finding in outcome.findings
        ]

        self.assertTrue(all(outcome.status == "complete" for outcome in outcomes))
        self.assertTrue(
            any(url.startswith("https://platform.opentargets.org/evidence/") for url in {f.url for f in findings})
        )
        self.assertIn("https://www.ebi.ac.uk/chembl/explore/compound/CHEMBL76", {f.url for f in findings})
        self.assertEqual(
            {finding.source_labels[finding.source] for finding in findings},
            {"Open Targets", "ChEMBL"},
        )
        self.assertTrue(
            all(finding.retrieval_paths[-1].operation for finding in findings)
        )
        roles = {finding.source: finding.evidence_role for finding in findings}
        self.assertEqual(roles["open_targets"], "evidence")
        self.assertEqual(roles["chembl"], "reference")
        chembl = next(finding for finding in findings if finding.source == "chembl")
        self.assertEqual(chembl.development_records[0].phase, "Phase 4")
        open_targets_call = next(
            arguments
            for operation, arguments in connector.calls
            if operation == "OpenTargets_get_evidence_by_datasource"
        )
        self.assertNotIn("datasourceIds", open_targets_call)

    def test_structured_lanes_preserve_the_complete_neutral_intent_bundle(self) -> None:
        queries = (
            SourceQueryIntent(
                text="malaria vaccine efficacy trial",
                tracks=("general",),
                document_refs=("document/b-0001",),
            ),
            SourceQueryIntent(
                text="malaria vaccine efficacy limitation",
                tracks=("counterfactual",),
                document_refs=("document/b-0002",),
            ),
        )
        intent = RetrievalIntent(
            scope_ref="efficacy",
            topic="clinical efficacy",
            description="Protective efficacy target",
            indication="malaria",
            intervention_class="vaccine",
            queries=queries,
        )

        requests = plan_requests([intent], sources=("ctis", "isrctn", "fda"))

        self.assertEqual(len(requests), 3)
        for request in requests:
            self.assertEqual(request.connector, "tooluniverse")
            self.assertEqual(request.intent_ids, tuple(query.intent_id for query in queries))
            self.assertEqual(request.input_queries, tuple(query.text for query in queries))
            self.assertEqual(
                request.document_refs,
                ("document/b-0001", "document/b-0002"),
            )
            self.assertEqual(request.tracks, ("general", "counterfactual"))
            self.assertEqual(request.option("ranking"), "all_input_queries")
        self.assertEqual(
            [request.operation for request in requests],
            [
                "CTIS_search_trials_filtered",
                "ISRCTN_search_trials_fielded",
                "FDA_search_drug_labels",
            ],
        )

    def test_structured_lanes_normalize_findings_with_source_provenance(self) -> None:
        connector = _MultiSourceToolUniverse()
        runtime = SearchRuntime(
            llm_client=_NoopLLM(),
            integrations={"tooluniverse": connector},
        )
        intent = RetrievalIntent(
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
        requests = plan_requests([intent], sources=("ctis", "isrctn", "fda"))

        with patch("services.searcher.controller._wait_for_source_start"):
            outcomes = run_requests(
                requests,
                runtime=runtime,
                max_tokens=100,
                max_uses=1,
            )

        self.assertTrue(all(outcome.status == "complete" for outcome in outcomes))
        findings = [outcome.findings[0] for outcome in outcomes]
        self.assertEqual([finding.source for finding in findings], ["ctis", "isrctn", "fda"])
        self.assertEqual(
            [finding.source_labels[finding.source] for finding in findings],
            ["EU CTIS", "ISRCTN", "FDA Regulatory"],
        )
        self.assertTrue(
            all(finding.source_attributions[finding.source] for finding in findings)
        )
        self.assertEqual(
            [finding.retrieval_paths[-1].operation for finding in findings],
            [request.operation for request in requests],
        )
        self.assertEqual(
            [call[1] for call in connector.calls],
            [
                {"medical_condition": "malaria", "limit": 50},
                {"condition": "malaria", "limit": 50, "intervention": "vaccine"},
                {"indication": "malaria", "limit": 20},
            ],
        )

    def test_fda_selects_the_device_operation_without_a_scout_branch(self) -> None:
        connector = _MultiSourceToolUniverse()
        runtime = SearchRuntime(
            llm_client=_NoopLLM(),
            integrations={"tooluniverse": connector},
        )
        intent = RetrievalIntent(
            scope_ref="diagnostic-performance",
            topic="diagnostic performance",
            description="Malaria diagnostic target",
            indication="malaria",
            intervention_class="diagnostic",
            queries=(SourceQueryIntent(text="malaria diagnostic sensitivity"),),
        )

        request = plan_requests([intent], sources=("fda",))[0]
        with patch("services.searcher.controller._wait_for_source_start"):
            outcome = run_requests(
                [request],
                runtime=runtime,
                max_tokens=100,
                max_uses=1,
            )[0]

        self.assertEqual(request.operation, "OpenFDA_search_device_510k")
        self.assertEqual(outcome.status, "complete")
        self.assertEqual(
            outcome.findings[0].url,
            "https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/"
            "cfpmn/pmn.cfm?ID=K260001",
        )

    def test_fda_safety_uses_named_products_and_keeps_noncausal_records(self) -> None:
        connector = _MultiSourceToolUniverse()
        runtime = SearchRuntime(
            llm_client=_NoopLLM(),
            integrations={"tooluniverse": connector},
        )
        intent = RetrievalIntent(
            scope_ref="safety",
            topic="safety profile",
            description="Known and reported product safety signals",
            indication="malaria",
            intervention_class="drug",
            queries=(SourceQueryIntent(text="chloroquine safety warnings"),),
            evidence_domain="safety",
            entities=(RetrievalEntity("chloroquine", "drug"),),
        )

        requests = plan_requests([intent], sources=("fda_safety",))
        with patch("services.searcher.controller._wait_for_source_start"):
            outcomes = run_requests(
                requests,
                runtime=runtime,
                max_tokens=100,
                max_uses=1,
            )

        self.assertEqual(
            [request.operation for request in requests],
            [
                "FDA_get_warnings_by_drug_name",
                "FAERS_count_reactions_by_drug_event",
            ],
        )
        self.assertTrue(all(outcome.status == "complete" for outcome in outcomes))
        observations = [
            record
            for outcome in outcomes
            for finding in outcome.findings
            for record in finding.safety_observations
        ]
        self.assertEqual(
            {
                (record.record_type, record.source_system)
                for record in observations
            },
            {("label_warning", "fda_label"), ("reported_event", "faers")},
        )
        reported = next(
            record
            for record in observations
            if record.record_type == "reported_event"
        )
        label_warning = next(
            record
            for record in observations
            if record.record_type == "label_warning"
        )
        self.assertEqual(reported.report_count, 12)
        self.assertIsNone(label_warning.report_count)
        self.assertIn("do not establish", reported.qualification)
        roles_by_type = {
            finding.safety_observations[0].record_type: finding.evidence_role
            for outcome in outcomes
            for finding in outcome.findings
            if finding.safety_observations
        }
        self.assertEqual(roles_by_type["label_warning"], "evidence")
        self.assertEqual(roles_by_type["reported_event"], "reference")

    def test_safety_observation_contract_rejects_invalid_source_counts(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown safety source system"):
            SafetyObservationRecord(
                product_name="Example drug",
                record_type="reported_event",
                source_system="unknown_source",
                label="Nausea",
                report_count=12,
            )
        with self.assertRaisesRegex(ValueError, "FAERS report count is required"):
            SafetyObservationRecord(
                product_name="Example drug",
                record_type="reported_event",
                source_system="faers",
                label="Nausea",
            )
        with self.assertRaisesRegex(ValueError, "only FAERS observations"):
            SafetyObservationRecord(
                product_name="Example device",
                record_type="recall",
                source_system="fda_recall",
                label="Class II",
                report_count=1,
            )
        with self.assertRaisesRegex(ValueError, "cannot be negative"):
            SafetyObservationRecord(
                product_name="Example drug",
                record_type="reported_event",
                source_system="faers",
                label="Nausea",
                report_count=-1,
            )

    def test_fda_safety_normalizes_device_events_and_recalls_separately(self) -> None:
        runtime = SearchRuntime(
            llm_client=_NoopLLM(),
            integrations={"tooluniverse": _MultiSourceToolUniverse()},
        )
        intent = RetrievalIntent(
            scope_ref="safety",
            topic="device safety profile",
            description="Known device reports and recalls",
            indication="malaria",
            intervention_class="diagnostic",
            queries=(SourceQueryIntent(text="malaria assay safety"),),
            evidence_domain="safety",
            entities=(RetrievalEntity("Example assay", "device"),),
        )

        requests = plan_requests([intent], sources=("fda_safety",))
        with patch("services.searcher.controller._wait_for_source_start"):
            outcomes = run_requests(
                requests,
                runtime=runtime,
                max_tokens=100,
                max_uses=1,
            )

        observations = [
            observation
            for outcome in outcomes
            for finding in outcome.findings
            for observation in finding.safety_observations
        ]
        self.assertEqual(
            {
                (observation.record_type, observation.source_system)
                for observation in observations
            },
            {("device_event", "maude"), ("recall", "fda_recall")},
        )
        self.assertTrue(
            all(observation.report_count is None for observation in observations)
        )

    def test_faers_source_url_preserves_the_native_unquoted_product_query(self) -> None:
        connector = _MultiSourceToolUniverse()
        runtime = SearchRuntime(
            llm_client=_NoopLLM(),
            integrations={"tooluniverse": connector},
        )
        intent = RetrievalIntent(
            scope_ref="safety",
            topic="safety profile",
            description="Known and reported product safety signals",
            indication="tuberculosis",
            intervention_class="drug",
            queries=(SourceQueryIntent(text="CAB-LA safety reports"),),
            evidence_domain="safety",
            entities=(RetrievalEntity("CAB-LA", "drug"),),
        )

        requests = plan_requests([intent], sources=("fda_safety",))
        with patch("services.searcher.controller._wait_for_source_start"):
            outcomes = run_requests(
                requests,
                runtime=runtime,
                max_tokens=100,
                max_uses=1,
            )

        reported_finding = next(
            finding
            for outcome in outcomes
            for finding in outcome.findings
            if finding.safety_observations
            and finding.safety_observations[0].record_type == "reported_event"
        )
        self.assertEqual(
            reported_finding.url,
            "https://api.fda.gov/drug/event.json?"
            "search=patient.drug.medicinalproduct%3ACAB-LA&"
            "count=patient.reaction.reactionmeddrapt.exact",
        )

    def test_global_worker_limit_bounds_future_source_fanout(self) -> None:
        connector = _CountingToolUniverse()
        runtime = SearchRuntime(
            llm_client=_NoopLLM(),
            integrations={"tooluniverse": connector},
            global_worker_limit=2,
        )
        requests = plan_requests(
            [
                RetrievalIntent(
                    scope_ref=f"field-{index}",
                    topic="efficacy",
                    description="",
                    indication="malaria",
                    intervention_class="vaccine",
                    queries=(SourceQueryIntent(text=f"query {index}"),),
                )
                for index in range(8)
            ],
            sources=("semantic_scholar",),
        )

        with patch("services.searcher.controller._wait_for_source_start"):
            run_requests(
                requests,
                runtime=runtime,
                max_tokens=100,
                max_uses=1,
            )

        self.assertEqual(connector.max_active, 2)

    def test_progress_counter_survives_multiple_scheduler_waves(self) -> None:
        connector = _FakeToolUniverse()
        runtime = SearchRuntime(
            llm_client=_NoopLLM(),
            integrations={"tooluniverse": connector},
            global_worker_limit=1,
        )
        requests = plan_requests(
            [
                RetrievalIntent(
                    scope_ref=f"field-{index}",
                    topic="efficacy",
                    description="",
                    indication="malaria",
                    intervention_class="vaccine",
                    queries=(SourceQueryIntent(text=f"query {index}"),),
                )
                for index in range(2)
            ],
            sources=("semantic_scholar",),
        )
        updates: list[tuple[int, int]] = []

        with patch("services.searcher.controller._wait_for_source_start"):
            outcomes = run_requests(
                requests,
                runtime=runtime,
                max_tokens=100,
                max_uses=1,
                progress=lambda completed, total: updates.append((completed, total)),
            )

        self.assertEqual(len(outcomes), 2)
        self.assertEqual(updates, [(0, 2), (1, 2), (2, 2)])

    def test_slow_lane_does_not_occupy_fast_lane_worker(self) -> None:
        web_started = threading.Event()
        connector = _CoordinatedToolUniverse(web_started)
        runtime = SearchRuntime(
            llm_client=_CoordinatedLLM(web_started),
            integrations={"tooluniverse": connector},
            global_worker_limit=2,
        )
        requests = [
            SearchRequest(
                scope_ref=f"field-{index}",
                source="semantic_scholar",
                query=f"paper query {index}",
            )
            for index in range(4)
        ]
        requests.append(
            SearchRequest(
                scope_ref="field-web",
                source="web",
                query="web query",
            )
        )

        with patch("services.searcher.controller._wait_for_source_start"):
            outcomes = run_requests(
                requests,
                runtime=runtime,
                max_tokens=100,
                max_uses=1,
            )

        self.assertTrue(connector.observed_web_start)
        self.assertEqual([outcome.request for outcome in outcomes], requests)


if __name__ == "__main__":
    unittest.main()
