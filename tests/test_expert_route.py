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
        "intervention_class": ["vaccine"],
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

    def test_an_unknown_gate_is_refused(self) -> None:
        response = self.post([docx()], gate=["no-such-gate"])
        self.assertEqual(response.status_code, 404)
        self.assertIn("question bank", response.json()["detail"])

    def test_an_unknown_document_type_is_refused(self) -> None:
        response = self.post([docx()], source_types=["pdss"])
        self.assertEqual(response.status_code, 404)

    def test_mismatched_context_lists_are_refused(self) -> None:
        response = self.post([docx()], context_labels=["CMC Report"])
        self.assertEqual(response.status_code, 400)
        self.assertIn("label and text", response.json()["detail"])

    def test_two_context_items_sharing_a_label_are_refused(self) -> None:
        response = self.post(
            [docx()],
            context_labels=["Report", "Report"],
            context_texts=["one", "two"],
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("share a label", response.json()["detail"])

    def test_a_missing_gate_field_is_refused(self) -> None:
        response = self.post([docx()], gate=None)
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
