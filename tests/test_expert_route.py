"""Expert's route rejects a bad request before it opens a stream.

Every guard here exists so a failure is an HTTP status the interface can show,
rather than an error event arriving on a 200 response after the upload was read.
"""

from __future__ import annotations

import io
import unittest

from fastapi.testclient import TestClient

from api.main import app


def form(**overrides) -> dict:
    data = {
        "source_types": ["itpp"],
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


def context(name: str = "notes.md", body: bytes = b"Agreed 24 months.") -> tuple:
    """One context attachment. Markdown, so the guard under test is the one that runs."""
    return ("context_files", (name, io.BytesIO(body), "text/markdown"))


class GatesEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_gates_are_published_in_development_order(self) -> None:
        response = self.client.get("/api/expert/gates")
        self.assertEqual(response.status_code, 200)
        gates = response.json()["gates"]
        self.assertTrue(gates)
        self.assertEqual(
            [gate["ordinal"] for gate in gates],
            sorted(gate["ordinal"] for gate in gates),
        )

    def test_an_unknown_org_publishes_no_gates(self) -> None:
        response = self.client.get("/api/expert/gates", params={"org": "nobody"})
        self.assertEqual(response.json()["gates"], [])


class RunGuardTests(unittest.TestCase):
    """Each guard fails the request rather than the stream."""

    def setUp(self) -> None:
        self.client = TestClient(app)

    def post(self, files, **overrides):
        return self.client.post("/api/expert/run", files=files, data=form(**overrides))

    def test_a_document_without_a_type_is_refused(self) -> None:
        response = self.post([docx(), docx("plan.docx")])
        self.assertEqual(response.status_code, 400)
        self.assertIn("document type", response.json()["detail"])

    def test_an_unsupported_format_is_refused(self) -> None:
        response = self.post(
            [("files", ("profile.pdf", io.BytesIO(b"%PDF"), "application/pdf"))]
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("DOCX", response.json()["detail"])

    def test_two_documents_with_one_filename_are_refused(self) -> None:
        response = self.post(
            [docx(), docx()], source_types=["itpp", "ipdp"]
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("distinct filename", response.json()["detail"])

    def test_two_documents_of_one_type_are_refused(self) -> None:
        response = self.post(
            [docx("a.docx"), docx("b.docx")], source_types=["itpp", "itpp"]
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("different type", response.json()["detail"])

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
        drug = self.client.get("/api/expert/gates", params={"intervention": "drug"})
        vaccine = self.client.get("/api/expert/gates", params={"intervention": "vaccine"})
        self.assertTrue(drug.json()["gates"])
        self.assertEqual(vaccine.json()["gates"], [])

    def test_an_unknown_gate_is_refused(self) -> None:
        response = self.post([docx()], gate=["no-such-gate"])
        self.assertEqual(response.status_code, 404)
        self.assertIn("question bank", response.json()["detail"])

    def test_an_unknown_document_type_is_refused(self) -> None:
        response = self.post([docx()], source_types=["pdss"])
        self.assertEqual(response.status_code, 404)

    def test_a_context_attachment_without_a_label_is_refused(self) -> None:
        """The label is what an answer is attributed to, so it cannot be absent."""
        response = self.post([docx(), context()])
        self.assertEqual(response.status_code, 400)
        self.assertIn("label", response.json()["detail"])

    def test_two_context_items_sharing_a_label_are_refused(self) -> None:
        response = self.post(
            [docx(), context("a.md"), context("b.md")],
            context_labels=["Report", "Report"],
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("share a label", response.json()["detail"])

    def test_a_context_format_the_reader_refuses_fails_before_the_stream(self) -> None:
        """A PPTX is a fine document and not context: it would be read as flat prose,
        losing the structure that makes it citable in the first place."""
        response = self.post(
            [docx(), context("deck.pptx")],
            context_labels=["Deck"],
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("deck.pptx", response.json()["detail"])

    def test_a_scanned_pdf_is_refused_with_the_reason(self) -> None:
        """Silence here would be a named source that answers nothing."""
        response = self.post(
            [docx(), context("scan.pdf", b"not a pdf at all")],
            context_labels=["Scan"],
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("scan.pdf", response.json()["detail"])

    def test_an_empty_context_attachment_is_refused(self) -> None:
        response = self.post(
            [docx(), context("empty.md", b"")],
            context_labels=["Empty"],
        )
        self.assertEqual(response.status_code, 400)

    def test_a_missing_gate_field_is_refused(self) -> None:
        response = self.post([docx()], gate=None)
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
