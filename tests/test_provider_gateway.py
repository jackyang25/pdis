"""Gateway routing preserves direct-provider use and explicit test injection."""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from api.deps import get_openai_client, get_quantitative_anthropic_client
from shared.anthropic_client import AnthropicQuantitativeClient
from shared.openai_client import OpenAIClient


class ProviderGatewayTests(unittest.TestCase):
    def test_credentials_and_endpoint_are_selected_together(self):
        providers = [
            (OpenAIClient, "openai.OpenAI", "OPENAI_API_KEY", "OPENAI_BASE_URL",
             "https://ai-kong-gateway.bmgf.io/ai/v2"),
            (AnthropicQuantitativeClient, "anthropic.Anthropic", "ANTHROPIC_API_KEY",
             "ANTHROPIC_BASE_URL", "https://ai-kong-gateway.bmgf.io/v2/anthropic"),
        ]
        for client_type, sdk, key_name, url_name, gateway in providers:
            cases = [
                ("direct", {key_name: "direct-test"}, {}, "direct-test", None),
                ("kong_only", {"KONG_KEY": "kong-test"}, {}, "kong-test", gateway),
                ("kong_precedence", {"KONG_KEY": "kong-test", key_name: "direct-test"},
                 {}, "kong-test", gateway),
                ("explicit_key", {"KONG_KEY": "kong-test"},
                 {"api_key": "explicit-test"}, "explicit-test", None),
                ("kong_url", {"KONG_KEY": "kong-test", url_name: "https://proxy.example.test"},
                 {}, "kong-test", "https://proxy.example.test"),
                ("direct_url", {key_name: "direct-test", url_name: "https://proxy.example.test"},
                 {}, "direct-test", "https://proxy.example.test"),
                ("explicit_url", {"KONG_KEY": "kong-test", url_name: "https://env.example.test"},
                 {"base_url": "https://explicit.example.test"},
                 "kong-test", "https://explicit.example.test"),
                ("blank_kong", {"KONG_KEY": "   ", key_name: "direct-test"},
                 {}, "direct-test", None),
            ]
            for name, env, kwargs, expected_key, expected_url in cases:
                with self.subTest(provider=client_type.__name__, case=name):
                    with patch.dict(os.environ, env, clear=True), patch(sdk) as constructor:
                        client_type(**kwargs)
                        constructor.assert_called_once_with(
                            api_key=expected_key, base_url=expected_url,
                        )

    def test_api_dependencies_accept_gateway_without_provider_keys(self):
        for dependency, constructor_path in [
            (get_openai_client, "api.deps.OpenAIClient"),
            (get_quantitative_anthropic_client, "api.deps.AnthropicQuantitativeClient"),
        ]:
            with self.subTest(dependency=dependency.__name__):
                with patch.dict(os.environ, {"KONG_KEY": "kong-test"}, clear=True):
                    with patch(constructor_path) as constructor:
                        self.assertIs(dependency(), constructor.return_value)
                        constructor.assert_called_once_with()
