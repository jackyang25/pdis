import threading
import unittest
from unittest.mock import patch

from pydantic import ValidationError

from api.schemas import SearcherRunResponse
from services.searcher import SearchReport, SearchRuntime


class _Client:
    def search_web(self, query, *, max_tokens, max_uses):
        return []


class SearchInputTests(unittest.TestCase):
    def test_query_must_contain_text(self) -> None:
        from api.operations.searcher import SearchInput

        with self.assertRaises(ValidationError):
            SearchInput(query="   ")

    def test_entities_have_closed_types_nonempty_names_and_no_extra_fields(
        self,
    ) -> None:
        from api.operations.searcher import SearchInput

        for entity in (
            {"name": "BRAF", "entity_type": "imaginary"},
            {"name": "   ", "entity_type": "gene"},
            {"name": "BRAF", "entity_type": "gene", "identifier": "HGNC:1097"},
        ):
            with self.subTest(entity=entity), self.assertRaises(ValidationError):
                SearchInput(query="BRAF evidence", entities=[entity])

    def test_unknown_top_level_fields_are_refused(self) -> None:
        from api.operations.searcher import SearchInput

        with self.assertRaises(ValidationError):
            SearchInput(query="RSV", provider="caller-choice")

    def test_nonempty_constraints_are_declared_in_the_json_schema(self) -> None:
        from api.operations.searcher import SearchInput

        schema = SearchInput.model_json_schema()
        self.assertEqual(schema["properties"]["query"]["pattern"], r"\S")
        self.assertEqual(
            schema["$defs"]["SearchEntityInput"]["properties"]["name"]["pattern"],
            r"\S",
        )


class SearchOperationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime = SearchRuntime(llm_client=_Client())

    def test_source_discovery_maps_registry_metadata_and_configuration(self) -> None:
        from api.operations.searcher import list_sources

        with patch("api.operations.searcher.get_search_integrations", return_value={}):
            sources = list_sources()

        web = next(source for source in sources if source.key == "web")
        self.assertTrue(web.configured)
        self.assertIn("text", web.reads)
        optional = [source for source in sources if not source.configured]
        self.assertTrue(
            optional, "an integration-backed source should report unconfigured"
        )

    def test_prepare_refuses_unknown_and_unconfigured_sources_with_codes(self) -> None:
        from api.operations.errors import OperationError
        from api.operations.searcher import SearchInput, prepare_search

        with patch(
            "api.operations.searcher.get_search_runtime", return_value=self.runtime
        ):
            with self.assertRaises(OperationError) as unknown:
                prepare_search(SearchInput(query="RSV", sources=["not-a-source"]))
            self.assertEqual(unknown.exception.code, "invalid_sources")

            with self.assertRaises(OperationError) as unavailable:
                prepare_search(SearchInput(query="RSV", sources=["semantic_scholar"]))
            self.assertEqual(unavailable.exception.code, "unconfigured_sources")

    def test_execute_forwards_all_facets_and_serializes_the_existing_result_shape(
        self,
    ) -> None:
        from api.operations.searcher import SearchInput, execute_search, prepare_search

        request = SearchInput(
            query="  RSV evidence  ",
            sources=["web"],
            condition=" respiratory infection ",
            intervention=" vaccine ",
            entities=[{"name": " RSV F ", "entity_type": "protein"}],
            product=" candidate 1 ",
            population=" older adults ",
            outcome=" efficacy ",
            region=" LMIC ",
            published_since=" 2025-01-01 ",
        )
        progress = lambda *args: None
        with (
            patch(
                "api.operations.searcher.get_search_runtime", return_value=self.runtime
            ),
            patch(
                "api.operations.searcher.run_pipeline", return_value=SearchReport()
            ) as run,
        ):
            result = execute_search(prepare_search(request), progress)

        self.assertIsInstance(result, SearcherRunResponse)
        self.assertEqual(
            result.model_dump(),
            {"query": "  RSV evidence  ", "findings": [], "lanes": []},
        )
        run.assert_called_once_with(
            "  RSV evidence  ",
            runtime=self.runtime,
            sources=("web",),
            condition="respiratory infection",
            intervention="vaccine",
            entities=(run.call_args.kwargs["entities"][0],),
            product="candidate 1",
            region="LMIC",
            published_since="2025-01-01",
            population="older adults",
            outcome="efficacy",
            progress_callback=progress,
        )
        entity = run.call_args.kwargs["entities"][0]
        self.assertEqual((entity.name, entity.entity_type), ("RSV F", "protein"))


class SharedCapacityTests(unittest.TestCase):
    def test_nonwaiting_caller_fails_fast_and_exception_releases_slot(self) -> None:
        import api.execution as execution

        original = execution._run_slots
        execution._run_slots = threading.Semaphore(1)
        self.addCleanup(setattr, execution, "_run_slots", original)

        with self.assertRaises(RuntimeError):
            with execution.run_slot():
                raise RuntimeError("failed work")

        with execution.run_slot(wait=False):
            with self.assertRaises(execution.CapacityExceeded):
                with execution.run_slot(wait=False):
                    pass

        with execution.run_slot(wait=False):
            pass


if __name__ == "__main__":
    unittest.main()
