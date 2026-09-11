"""Screener's route rejects a bad request before it opens a stream.

Every guard here exists so a failure is an HTTP status the interface can show,
rather than an error event arriving on a 200 response after the upload was read.
"""

from __future__ import annotations

import io
import unittest
import json
from unittest.mock import patch

from docx import Document

from fastapi.testclient import TestClient

from api.main import app
from tests.pdf_fixtures import pdf_bytes


def form(**overrides) -> dict:
    data = {
        "gate": ["lcs"],
        "org": ["bmgf"],
        # `drug`, because that is what these banks are written for. A vaccine request is
        # refused by the guard below, which would otherwise mask every later guard.
        "intervention_class": ["drug"],
        "indication": ["malaria"],
    }
    for key, value in overrides.items():
        if value is None:
            data.pop(key, None)
        else:
            data[key] = value
    return data


def docx(name: str = "profile.docx") -> tuple[str, tuple[str, io.BytesIO, str]]:
    return (
        "files",
        (
            name,
            io.BytesIO(b"not really a docx"),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
    )


class GatesEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_gates_are_published_in_development_order(self) -> None:
        response = self.client.get("/api/screener/gates")
        self.assertEqual(response.status_code, 200)
        gates = response.json()["gates"]
        self.assertTrue(gates)
        self.assertEqual(
            [gate["ordinal"] for gate in gates],
            sorted(gate["ordinal"] for gate in gates),
        )

    def test_an_unknown_org_publishes_no_gates(self) -> None:
        response = self.client.get("/api/screener/gates", params={"org": "nobody"})
        self.assertEqual(response.json()["gates"], [])


class RunGuardTests(unittest.TestCase):
    """Each guard fails the request rather than the stream."""

    def setUp(self) -> None:
        self.client = TestClient(app)

    def post(self, files, **overrides):
        return self.client.post("/api/screener/run", files=files, data=form(**overrides))

    def test_legacy_input_fields_are_refused_not_ignored(self) -> None:
        for field in ("source_types", "context_labels"):
            with self.subTest(field=field):
                response = self.post([docx()], **{field: ["old"]})
                self.assertEqual(response.status_code, 400)
                self.assertIn(field, response.json()["detail"])
        response = self.post([docx(), ("context_files", ("notes.md", b"notes", "text/markdown"))])
        self.assertEqual(response.status_code, 400)
        self.assertIn("context_files", response.json()["detail"])

    def test_standalone_images_and_plain_text_are_refused(self) -> None:
        for suffix in ("png", "jpg", "txt", "md"):
            with self.subTest(suffix=suffix):
                response = self.post([("files", ("report." + suffix, b"data", "application/octet-stream"))])
                self.assertEqual(response.status_code, 400)

    def test_multiple_untyped_documents_reach_the_retained_result(self) -> None:
        from tests.test_screener_pipeline import ScriptedClient

        uploads = []
        for filename, text in (("report.docx", "Laboratory evidence."), ("minutes.docx", "Study planning.")):
            document = Document()
            document.add_paragraph(text)
            payload = io.BytesIO()
            document.save(payload)
            uploads.append(("files", (filename, payload.getvalue(), "application/octet-stream")))
        with patch("api.routes.screener.get_openai_client", return_value=ScriptedClient([])):
            response = self.post(uploads)
        self.assertEqual(response.status_code, 200)
        events = [json.loads(line) for line in response.text.splitlines() if line]
        self.assertFalse([event for event in events if event.get("event") == "error"], events)
        completed = next(event for event in events if event.get("event") == "complete")
        review = completed["result"]["review"]
        self.assertEqual(review["documents"], [{"doc_id": "report"}, {"doc_id": "minutes"}])
        self.assertEqual({block["doc_id"] for block in review["blocks"]}, {"report", "minutes"})

    def test_an_unsupported_format_is_refused(self) -> None:
        response = self.post(
            [("files", ("profile.rtf", io.BytesIO(b"data"), "application/rtf"))]
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("DOCX", response.json()["detail"])

    def test_pdf_and_docx_share_the_retained_citation_collection(self):
        from tests.test_screener_pipeline import ScriptedClient
        document = Document()
        document.add_paragraph("Supporting plan.")
        payload = io.BytesIO()
        document.save(payload)
        client = ScriptedClient([{
            "decision": "answered", "statement": "The trial is planned.",
            "missing": "", "block_ids": ["study/b-0001"],
        }])
        with patch("api.routes.screener.get_openai_client", return_value=client):
            response = self.post([
                ("files", ("study.PDF", pdf_bytes("The trial is planned.", image_pages=(1,)), "application/pdf")),
                ("files", ("plan.docx", payload.getvalue(), "application/octet-stream")),
            ])
        self.assertEqual(response.status_code, 200)
        events = [json.loads(line) for line in response.text.splitlines()]
        self.assertFalse([e for e in events if e["event"] == "error"], events)
        review = next(e["result"]["review"] for e in events if e["event"] == "complete")
        self.assertEqual(review["documents"], [{"doc_id": "study"}, {"doc_id": "plan"}])
        self.assertEqual({b["doc_id"] for b in review["blocks"]}, {"study", "plan"})
        self.assertEqual(review["blocks"][0]["structural_meta"]["page"], 1)
        self.assertEqual(review["blocks"][1]["id"], "study/b-0001-image-0001")
        self.assertTrue(review["blocks"][1]["image"]["data_base64"])
        self.assertTrue(any(q["cited_block_ids"] == ["study/b-0001"]
                            for d in review["disciplines"] for q in d["questions"]))
        self.assertTrue(all("The trial is planned." in call and "Supporting plan." in call
                            for call in client.triage_calls))

    def test_unreadable_pdf_fails_without_assessment_or_partial_result(self):
        from tests.test_screener_pipeline import ScriptedClient
        client = ScriptedClient([])
        with patch("api.routes.screener.get_openai_client", return_value=client):
            response = self.post([("files", ("study.pdf", pdf_bytes("Text", None), "application/pdf"))])
        events = [json.loads(line) for line in response.text.splitlines()]
        self.assertTrue(any(e["event"] == "error" for e in events), events)
        self.assertFalse(any(e["event"] == "complete" for e in events))
        self.assertEqual(client.triage_calls, [])

    def test_other_document_routes_still_refuse_pdf(self):
        data = {"org": "bmgf", "source_type": "itpp", "intervention_class": "drug", "indication": "malaria"}
        for tool in ("chunker", "inspector", "scout"):
            with self.subTest(tool=tool):
                response = self.client.post(f"/api/{tool}/run", data=data,
                    files={"files" if tool == "scout" else "file":
                           ("study.pdf", pdf_bytes("Text"), "application/pdf")})
                self.assertEqual(response.status_code, 400, response.text)
                self.assertIn("DOCX", response.json()["detail"])

    def test_aligner_still_refuses_pdf_with_an_otherwise_valid_document_pair(self):
        response = self.client.post("/api/aligner/run", data={
            "org": "bmgf", "source_types": ["itpp", "ctpp"],
            "intervention_class": "drug", "indication": "malaria",
        }, files=[
            ("files", ("reference.pdf", pdf_bytes("Text"), "application/pdf")),
            ("files", ("candidate.docx", b"unused", "application/octet-stream")),
        ])
        self.assertEqual(response.status_code, 400, response.text)
        self.assertIn("DOCX", response.json()["detail"])

    def test_two_documents_with_one_filename_are_refused(self) -> None:
        response = self.post(
            [docx(), docx()]
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("distinct filename", response.json()["detail"])

    def test_a_modality_the_bank_does_not_serve_is_refused(self) -> None:
        """These banks ask about synthetic routes and salt forms. Returning a review in
        which every question is inapplicable would read like a review that found nothing
        wrong."""
        response = self.post([docx()], intervention_class=["vaccine"])
        self.assertEqual(response.status_code, 400)
        detail = response.json()["detail"]
        self.assertIn("drug", detail)
        self.assertIn("vaccine", detail)

    def test_the_gate_list_offers_nothing_for_a_modality_no_bank_covers(self) -> None:
        """Surfaced where the gate is chosen, so the refusal above is a backstop rather
        than the first a reader hears of it."""
        drug = self.client.get("/api/screener/gates", params={"intervention": "drug"})
        vaccine = self.client.get("/api/screener/gates", params={"intervention": "vaccine"})
        self.assertTrue(drug.json()["gates"])
        self.assertEqual(vaccine.json()["gates"], [])

    def test_an_unknown_gate_is_refused(self) -> None:
        response = self.post([docx()], gate=["no-such-gate"])
        self.assertEqual(response.status_code, 404)
        self.assertIn("question bank", response.json()["detail"])

    def test_a_missing_gate_field_is_refused(self) -> None:
        response = self.post([docx()], gate=None)
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
