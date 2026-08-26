"""Inspector's route hands the pipeline arguments it can actually build.

Written for a real failure: `startup: name 'doc_id' is not defined`. The route discarded
the document id into `_` and then passed `doc_id=doc_id` twenty lines later, so every run
raised `NameError` the moment it reached the pipeline. Nothing caught it because Python
binds names at run time, the call sits inside a worker function that only executes once a
request is in flight, and the failure arrives as an error event on an otherwise successful
stream rather than as a status code.

The other four upload routes bind both halves of `document_upload_parts`. Inspector was
the only one that did not.
"""

from __future__ import annotations

import io
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.main import app


class SENTINEL(Exception):
    """Raised by the stubbed pipeline, to prove the call was reached."""


def _run(**overrides) -> object:
    data = {
        "org": "bmgf",
        "source_type": "itpp",
        "intervention_class": "vaccine",
        "indication": "malaria",
    }
    data.update(overrides)
    client = TestClient(app, raise_server_exceptions=False)
    return client.post(
        "/api/inspector/run",
        files={
            "file": (
                "profile.docx",
                io.BytesIO(b"not really a docx"),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
        data=data,
    )


class RouteArgumentTests(unittest.TestCase):
    def test_the_pipeline_call_is_reached_with_every_argument_bound(self) -> None:
        """The regression. A stub that raises proves the arguments evaluated: an unbound
        name fails while building the call, before the stub can run at all.
        """
        with patch("api.routes.inspector.run_pipeline", side_effect=SENTINEL("reached")):
            body = _run().text
        self.assertNotIn("NameError", body, "an argument to run_pipeline is unbound")
        self.assertIn("reached", body, "the pipeline call was never made")

    def test_the_document_id_reaches_the_pipeline(self) -> None:
        """Not merely bound - bound to the uploaded document's id. Binding it to anything
        would satisfy the test above; the blocks are stamped with this value, and the whole
        result is keyed by it.
        """
        captured: dict[str, object] = {}

        def capture(*args, **kwargs):
            captured.update(kwargs)
            raise SENTINEL("reached")

        with patch("api.routes.inspector.run_pipeline", side_effect=capture):
            _run()
        self.assertEqual(captured.get("doc_id"), "profile")


if __name__ == "__main__":
    unittest.main()
