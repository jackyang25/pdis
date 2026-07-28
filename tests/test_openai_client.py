"""Server-owned task-tier selection for the shared OpenAI client."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from shared.openai_client import (
    DEFAULT_FAST_MODEL,
    DEFAULT_REASONING_MODEL,
    OpenAIClient,
)


class OpenAIClientConfigurationTests(unittest.TestCase):
    @patch("openai.OpenAI")
    def test_environment_selects_models_for_closed_task_tiers(self, _client: object) -> None:
        with patch.dict(os.environ, {
            "OPENAI_MODEL_FAST": "fast-test",
            "OPENAI_MODEL_REASONING": "reasoning-test",
        }):
            client = OpenAIClient(api_key="test-key")

        self.assertEqual(client.model_for("fast"), "fast-test")
        self.assertEqual(client.model_for("reasoning"), "reasoning-test")
        self.assertEqual(client.model, "reasoning-test")

    @patch("openai.OpenAI")
    def test_defaults_apply_when_tier_overrides_are_absent(self, _client: object) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("OPENAI_MODEL_FAST", None)
            os.environ.pop("OPENAI_MODEL_REASONING", None)
            default_client = OpenAIClient(api_key="test-key")

        self.assertEqual(default_client.model_for("fast"), DEFAULT_FAST_MODEL)
        self.assertEqual(default_client.model_for("reasoning"), DEFAULT_REASONING_MODEL)


if __name__ == "__main__":
    unittest.main()
