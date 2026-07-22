"""Process-level model selection for the shared OpenAI client."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from shared.openai_client import DEFAULT_MODEL, OpenAIClient


class OpenAIClientConfigurationTests(unittest.TestCase):
    @patch("openai.OpenAI")
    def test_environment_selects_one_model_for_the_process(self, _client: object) -> None:
        with patch.dict(os.environ, {"OPENAI_MODEL": "gpt-5-mini"}):
            client = OpenAIClient(api_key="test-key")

        self.assertEqual(client.model, "gpt-5-mini")

    @patch("openai.OpenAI")
    def test_default_and_explicit_model_precedence(self, _client: object) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("OPENAI_MODEL", None)
            default_client = OpenAIClient(api_key="test-key")
        with patch.dict(os.environ, {"OPENAI_MODEL": "gpt-5-mini"}):
            explicit_client = OpenAIClient(api_key="test-key", model="gpt-5.5")

        self.assertEqual(default_client.model, DEFAULT_MODEL)
        self.assertEqual(explicit_client.model, "gpt-5.5")


if __name__ == "__main__":
    unittest.main()
