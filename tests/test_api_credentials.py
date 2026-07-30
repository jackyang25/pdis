"""A missing server credential is a server error, not a 200 with an error event.

Provider clients are constructed inside each streaming worker, so an exception
raised there is caught by the streaming machinery and reported as an event on an
already-successful response. These tests pin the status code instead.
"""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.deps import MissingCredentialError, get_openai_client
from api.main import app


def _without(*names: str) -> dict[str, str]:
    return {
        key: value
        for key, value in os.environ.items()
        if key not in names
    }


class CredentialContractTests(unittest.TestCase):
    def test_a_missing_key_raises_a_domain_error_not_a_transport_error(self) -> None:
        with patch.dict(os.environ, _without("OPENAI_API_KEY"), clear=True):
            with self.assertRaises(MissingCredentialError):
                get_openai_client()

    def test_a_missing_key_fails_the_request_rather_than_the_stream(self) -> None:
        client = TestClient(app, raise_server_exceptions=False)
        with patch.dict(os.environ, _without("OPENAI_API_KEY"), clear=True):
            response = client.post(
                "/api/chunker/run",
                files={"file": ("doc.docx", b"not a real document", "application/octet-stream")},
                data={
                    "org": "bmgf",
                    "source_type": "itpp",
                    "intervention_class": "vaccine",
                    "indication": "malaria",
                },
            )

        self.assertEqual(response.status_code, 500)
        self.assertIn("OPENAI_API_KEY", response.json()["detail"])




class WireContractTests(unittest.TestCase):
    """The wire block carries every field the service's block carries."""

    def test_content_block_wire_shape_keeps_document_provenance(self) -> None:
        from dataclasses import fields

        from api.schemas import ContentBlockOut
        from services.chunker import ContentBlock

        service_fields = {field.name for field in fields(ContentBlock)}
        wire_fields = set(ContentBlockOut.model_fields)

        self.assertEqual(
            service_fields - wire_fields,
            set(),
            "the wire shape silently discards fields the service block carries",
        )


if __name__ == "__main__":
    unittest.main()
