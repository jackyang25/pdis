"""Untrusted form fields must be bounded before a tool starts work."""

import unittest

from fastapi.testclient import TestClient

from api.main import app


class FormSecurityTests(unittest.TestCase):
    def test_screener_allows_fields_at_limit_to_reach_validation(self):
        response = TestClient(app).post(
            "/api/screener/run",
            content="&".join(f"field{i}=value" for i in range(1000)),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        self.assertEqual(response.status_code, 422)

    def test_screener_rejects_excess_urlencoded_fields_before_validation(self):
        response = TestClient(app).post(
            "/api/screener/run",
            content="&".join(f"field{i}=value" for i in range(1001)),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Too many fields", response.json()["detail"])
