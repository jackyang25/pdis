"""Drafter's routes refuse a bad request before a stream opens, and export only final drafts."""

from __future__ import annotations

import io
import json
import unittest
from unittest.mock import patch

from docx import Document
from fastapi.testclient import TestClient

from api.deps import MissingCredentialError
from api.main import app
from services.drafter.models import DraftResult
from tests.test_drafter_contract import result as draft_result, suggested

FORM = {"org": "bmgf", "intervention_class": "vaccine", "indication": "malaria"}


class RunRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_an_unknown_product_type_is_404_before_any_work(self):
        response = self.client.post("/api/drafter/run", data={**FORM, "intervention_class": "widget"})
        self.assertEqual(response.status_code, 404)

    def test_an_unknown_disease_is_400(self):
        response = self.client.post("/api/drafter/run", data={**FORM, "indication": "not_a_disease"})
        self.assertEqual(response.status_code, 400)

    def test_a_missing_credential_fails_the_request_not_the_stream(self):
        with patch("api.routes.drafter.get_openai_client", side_effect=MissingCredentialError("no key")):
            response = self.client.post("/api/drafter/run", data=FORM)
        self.assertEqual(response.status_code, 500)

    def test_a_run_without_a_draft_streams_its_result(self):
        fake = DraftResult(org="bmgf", source_type="itpp", intervention_class="vaccine", indication="malaria",
                           display_name="Vaccine", sources=("pubmed",), failed_sources=(), unconfigured_sources=(), source_errors=(),
                           variables=())
        with patch("api.routes.drafter.get_openai_client", return_value=object()), \
             patch("api.routes.drafter.get_search_runtime", return_value=object()), \
             patch("api.routes.drafter.run_pipeline", return_value=fake) as run:
            response = self.client.post("/api/drafter/run", data=FORM)
        events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
        complete = [event for event in events if event["event"] == "complete"]
        self.assertEqual(complete[0]["result"]["result"]["indication"], "malaria")
        self.assertEqual(run.call_args.kwargs["indication"], "malaria")


class ExportRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_a_draft_exports_as_a_word_document(self):
        response = self.client.post("/api/drafter/export", json={"result": draft_result(suggested())})
        self.assertEqual(response.status_code, 200)
        self.assertIn("wordprocessingml", response.headers["content-type"])
        self.assertIn("pdis-drafter", response.headers["content-disposition"])
        Document(io.BytesIO(response.content))

    def test_a_malformed_draft_is_422(self):
        broken = draft_result(suggested())
        broken["variables"][0]["suggestion"]["basis_ids"] = []
        response = self.client.post("/api/drafter/export", json={"result": broken})
        self.assertEqual(response.status_code, 422)


class ContextSupportTests(unittest.TestCase):
    def test_contexts_publish_drafter_support_for_every_itpp_product_type(self):
        contexts = TestClient(app).get("/api/configs/contexts").json()["contexts"]
        supported = {item["intervention_class"] for item in contexts if item["supports"].get("drafter")}
        self.assertEqual(supported, {"vaccine", "drug", "diagnostic", "device"})


if __name__ == "__main__":
    unittest.main()
