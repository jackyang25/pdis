"""Every upload route applies one size bound, one empty-file rule and one identity rule.

Each guard fails the request before its stream opens, so the refusal is a status code
the interface can show rather than an error event on a 200.
"""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from docx import Document
from fastapi.testclient import TestClient

import api.uploads as uploads
from api.deps import MissingCredentialError
from api.main import app

CONTEXT = {"org": "bmgf", "intervention_class": "vaccine", "indication": "malaria"}
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def docx_bytes(text: str = "Target product profile.") -> bytes:
    document = Document()
    document.add_paragraph(text)
    payload = io.BytesIO()
    document.save(payload)
    return payload.getvalue()


def single(name: str, payload: bytes) -> dict:
    return {"file": (name, payload, DOCX)}


def several(*items: tuple[str, bytes]) -> list:
    return [("files", (name, payload, DOCX)) for name, payload in items]


# Route, form, files for one upload of `payload` named `name`.
def route_requests(name: str, payload: bytes):
    return {
        "chunker": ("/api/chunker/run", {**CONTEXT, "source_type": "itpp"}, single(name, payload)),
        "inspector": ("/api/inspector/run", {**CONTEXT, "source_type": "itpp"}, single(name, payload)),
        "scout": ("/api/scout/run", {**CONTEXT, "source_type": "itpp"}, several((name, payload))),
        "aligner": (
            "/api/aligner/run",
            {**CONTEXT, "source_types": ["itpp", "ctpp"]},
            several((name, payload), ("other.docx", b"x")),
        ),
        "screener": (
            "/api/screener/run",
            {**CONTEXT, "intervention_class": "drug", "gate": "lcs"},
            several((name, payload)),
        ),
    }


class UploadBoundTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app, raise_server_exceptions=False)
        # Small bounds, so the test need not build a 50 MB request.
        for name, value in (("MAX_UPLOAD_BYTES", 64), ("MAX_REQUEST_UPLOAD_BYTES", 100)):
            patcher = patch.object(uploads, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_an_oversized_file_is_refused_by_every_route(self) -> None:
        for tool, (url, data, files) in route_requests("big.docx", b"x" * 65).items():
            with self.subTest(tool=tool):
                response = self.client.post(url, data=data, files=files)
                self.assertEqual(response.status_code, 413, response.text)
                self.assertIn("big", response.json()["detail"])

    def test_an_empty_file_is_refused_by_every_route(self) -> None:
        for tool, (url, data, files) in route_requests("blank.docx", b"").items():
            with self.subTest(tool=tool):
                response = self.client.post(url, data=data, files=files)
                self.assertEqual(response.status_code, 400, response.text)
                self.assertIn("blank: the file is empty", response.json()["detail"])

    def test_files_within_the_bound_can_still_exceed_the_request_total(self) -> None:
        response = self.client.post(
            "/api/screener/run",
            data={**CONTEXT, "intervention_class": "drug", "gate": "lcs"},
            files=several(("a.docx", b"x" * 60), ("b.docx", b"x" * 60)),
        )
        self.assertEqual(response.status_code, 413, response.text)

    def test_an_assistant_attachment_has_the_same_bound(self) -> None:
        response = self.client.post(
            "/api/assistant/context", files={"file": ("notes.docx", b"x" * 65, DOCX)}
        )
        self.assertEqual(response.status_code, 413, response.text)


class DuplicateIdentityTests(unittest.TestCase):
    def test_two_documents_with_one_name_are_refused_by_every_multi_document_route(self) -> None:
        client = TestClient(app, raise_server_exceptions=False)
        requests = {
            "scout": ("/api/scout/run", {**CONTEXT, "source_type": "itpp"}),
            "aligner": ("/api/aligner/run", {**CONTEXT, "source_types": ["itpp", "ctpp"]}),
            "screener": ("/api/screener/run", {**CONTEXT, "intervention_class": "drug", "gate": "lcs"}),
        }
        for tool, (url, data) in requests.items():
            with self.subTest(tool=tool):
                response = client.post(
                    url, data=data, files=several(("plan.docx", b"a"), ("plan.docx", b"b"))
                )
                self.assertEqual(response.status_code, 400, response.text)
                self.assertIn("distinct filename", response.json()["detail"])


class ScoutTempFileTests(unittest.TestCase):
    def test_a_refused_request_leaves_no_temporary_file(self) -> None:
        """Uploads reach disk only inside the run, which always removes them."""
        client = TestClient(app, raise_server_exceptions=False)
        scratch = tempfile.mkdtemp()
        with patch.object(tempfile, "tempdir", scratch), patch(
            "api.routes.scout.get_openai_client",
            side_effect=MissingCredentialError("no key"),
        ):
            response = client.post(
                "/api/scout/run",
                data={**CONTEXT, "source_type": "itpp"},
                files=several(("plan.docx", docx_bytes())),
            )
        self.assertEqual(response.status_code, 500, response.text)
        self.assertEqual(os.listdir(scratch), [])


class ScoutLookupStatusTests(unittest.TestCase):
    def test_an_unknown_configuration_is_404_on_run_and_continue(self) -> None:
        client = TestClient(app, raise_server_exceptions=False)
        unknown = {"org": "nobody", "source_type": "itpp", "intervention_class": "vaccine",
                   "indication": "malaria"}
        run = client.post("/api/scout/run", data=unknown, files=several(("plan.docx", b"a")))
        self.assertEqual(run.status_code, 404, run.text)
        draft = {
            **unknown, "phase": "target_review",
            "context_validation": {"status": "match", "configured_indication": "malaria"},
            "quantitative_ledger": {"status": "not_applicable"},
            "retrieval_scope": {"entries": []},
            "variables": [], "matches": [], "assessments": [],
            "stats": {"queries": 0, "findings": 0, "unique_findings": 0, "insights": 0,
                      "matches": 0, "assessments": 0},
        }
        resumed = client.post("/api/scout/continue", json={"draft": draft})
        self.assertEqual(resumed.status_code, 404, resumed.text)


class AssistantAuxiliaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app, raise_server_exceptions=False)

    def test_a_corrupt_attachment_is_the_callers_error(self) -> None:
        response = self.client.post(
            "/api/assistant/context", files={"file": ("notes.docx", b"not a docx", DOCX)}
        )
        self.assertEqual(response.status_code, 400, response.text)
        self.assertNotIn("/tmp", response.json()["detail"])

    def test_attachments_and_readings_are_refused_when_their_capacity_is_spent(self) -> None:
        import threading

        import api.execution as execution

        with patch.object(execution, "_auxiliary_slots", threading.Semaphore(0)), patch(
            "api.routes.assistant.get_openai_client"
        ):
            attachment = self.client.post(
                "/api/assistant/context",
                files={"file": ("notes.docx", docx_bytes(), DOCX)},
            )
            reading = self.client.post(
                "/api/assistant/priorities",
                json={"authority": "Inspector reads a document against its rubric.",
                      "findings": [{"id": "u1", "subject": "Dose"}]},
            )
        self.assertEqual(attachment.status_code, 503, attachment.text)
        self.assertEqual(reading.status_code, 503, reading.text)


class ChunkerWireTests(unittest.TestCase):
    def test_a_chunker_block_keeps_its_source_format_and_provenance(self) -> None:
        from services.chunker import ContentBlock

        block = ContentBlock(
            id="plan/b-0001", doc_id="plan", ordinal=1, block_type="paragraph",
            content="Text", heading_stack=[], structural_meta={}, style_hint={},
            source_format="docx", org="bmgf", source_type="itpp",
            intervention_class="vaccine", indication="malaria",
        )
        client = TestClient(app, raise_server_exceptions=False)
        with patch("api.routes.chunker.get_openai_client"), patch(
            "api.routes.chunker.run_pipeline", return_value=[block]
        ):
            response = client.post(
                "/api/chunker/run",
                data={**CONTEXT, "source_type": "itpp"},
                files=single("plan.docx", b"bytes"),
            )
        events = [json.loads(line) for line in response.text.splitlines() if line]
        result = next(event["result"] for event in events if event["event"] == "complete")
        wire = result["blocks"][0]
        self.assertEqual(wire["source_format"], "docx")
        self.assertEqual(
            (wire["org"], wire["source_type"], wire["intervention_class"], wire["indication"]),
            ("bmgf", "itpp", "vaccine", "malaria"),
        )


if __name__ == "__main__":
    unittest.main()
