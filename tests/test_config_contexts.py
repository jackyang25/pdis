"""Context discovery is independent of document taxonomy for Screener."""

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.main import app
from services.screener import find_config
from shared.vocabulary import indications_for, intervention_classes, search_term


class ContextDiscoveryTests(unittest.TestCase):
    def test_indication_options_preserve_context_keys_through_discovery(self):
        client = TestClient(app)
        for intervention in intervention_classes():
            with self.subTest(intervention=intervention):
                response = client.get("/api/configs/indications", params={"intervention": intervention})
                self.assertEqual(response.status_code, 200)
                options = response.json()["indications"]
                self.assertEqual(options, indications_for(intervention))
                self.assertIn("postpartum_hemorrhage", options)
                self.assertIn("type_2_diabetes", options)
                self.assertEqual(search_term("postpartum_hemorrhage"), "postpartum hemorrhage")
                self.assertIn("respiratory_syncytial_virus", options)
                self.assertNotIn("rsv", options)
        self.assertEqual(client.get("/api/configs/indications", params={
            "intervention": "unsupported_class",
        }).json(), {"indications": []})

    def test_screener_contexts_exist_without_any_chunker_configuration(self):
        bank = find_config("bmgf", "lcs")
        with patch("api.routes.configs.available_chunker_configs", return_value=[]), patch(
            "api.routes.configs.available_screener_configs", return_value=[bank]
        ):
            response = TestClient(app).get("/api/configs/contexts")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            "contexts": [{"org": "bmgf", "intervention_class": "drug",
                          "supports": {"screener": True}}],
        })

    def test_document_types_do_not_claim_screener_support(self):
        response = TestClient(app).get("/api/configs/document-types")
        self.assertEqual(response.status_code, 200)
        for entry in response.json()["document_types"]:
            self.assertNotIn("screener", entry["supports"])

    def test_contexts_combine_tool_support_once_per_org_and_intervention(self):
        response = TestClient(app).get("/api/configs/contexts")
        self.assertEqual(response.status_code, 200)
        contexts = response.json()["contexts"]
        keys = [(entry["org"], entry["intervention_class"]) for entry in contexts]
        self.assertEqual(len(keys), len(set(keys)))
        drug = next(entry for entry in contexts if entry["org"] == "bmgf" and entry["intervention_class"] == "drug")
        self.assertTrue(drug["supports"]["screener"])
        self.assertTrue(drug["supports"]["chunker"])

    def test_a_malformed_bank_is_not_silently_hidden(self):
        with patch("api.routes.configs.available_screener_configs", side_effect=ValueError("broken bank")):
            with self.assertRaisesRegex(ValueError, "broken bank"):
                TestClient(app).get("/api/configs/contexts")


if __name__ == "__main__":
    unittest.main()
