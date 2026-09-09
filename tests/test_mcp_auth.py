import os
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from api.mcp.auth import JWTVerifier
from api.mcp.settings import MCPSettings, load_mcp_settings


class SettingsTests(unittest.TestCase):
    def test_disabled_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(load_mcp_settings())

    def test_enabled_requires_configuration(self):
        with patch.dict(os.environ, {"PDIS_MCP_ENABLED": "true"}, clear=True):
            with self.assertRaises(ValueError):
                load_mcp_settings()

    def test_refuses_insecure_or_wrong_endpoint(self):
        for url in ("http://pdis.example/api/mcp", "https://pdis.example/wrong"):
            with self.assertRaises(ValueError):
                MCPSettings(
                    url=url,
                    issuer="https://id.example/",
                    jwks_url="https://id.example/keys",
                    audience="pdis",
                )

    def test_browser_origins_must_be_exact_not_wildcards_or_invalid_hosts(self):
        for origin in (
            "https://*.example",
            "https://bad host.example",
            "http://client.example",
            "https://client.example/path",
        ):
            with self.subTest(origin=origin), self.assertRaises(ValueError):
                MCPSettings(
                    url="https://pdis.example/api/mcp",
                    issuer="https://id.example/",
                    jwks_url="https://id.example/keys",
                    audience="pdis",
                    browser_origins=(origin,),
                )


class JWTTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.settings = MCPSettings(
            url="https://pdis.example/api/mcp",
            issuer="https://id.example/",
            jwks_url="https://id.example/keys",
            audience="pdis",
        )
        self.verifier = JWTVerifier(self.settings)
        self.lookup = patch.object(
            self.verifier.jwks,
            "get_signing_key_from_jwt",
            return_value=SimpleNamespace(key=self.key.public_key()),
        )
        self.lookup.start()
        self.addCleanup(self.lookup.stop)

    def token(self, **changes):
        claims = {
            "iss": "https://id.example/",
            "aud": "pdis",
            "sub": "employee",
            "exp": int(time.time()) + 300,
            "scope": "pdis:search",
            "client_id": "client",
        }
        claims.update(changes)
        return jwt.encode(claims, self.key, algorithm="RS256", headers={"kid": "test"})

    async def test_accepts_valid_employee_token(self):
        result = await self.verifier.verify_token(self.token())
        self.assertEqual(result.subject, "employee")
        self.assertEqual(result.scopes, ["pdis:search"])
        self.assertEqual(result.resource, "https://pdis.example/api/mcp")

    async def test_rejects_wrong_issuer_audience_expiry_and_missing_subject(self):
        for changes in (
            {"iss": "https://attacker.example/"},
            {"aud": "another-api"},
            {"exp": 1},
            {"sub": ""},
        ):
            with self.subTest(changes=changes):
                self.assertIsNone(
                    await self.verifier.verify_token(self.token(**changes))
                )

    async def test_rejects_wrong_signature_and_unsigned_tokens(self):
        other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        bad = jwt.encode(
            {
                "iss": self.settings.issuer,
                "aud": "pdis",
                "sub": "x",
                "exp": int(time.time()) + 60,
            },
            other,
            algorithm="RS256",
        )
        self.assertIsNone(await self.verifier.verify_token(bad))
        self.assertIsNone(await self.verifier.verify_token("not-a-token"))

    async def test_jwks_failure_fails_closed(self):
        with patch.object(
            self.verifier.jwks,
            "get_signing_key_from_jwt",
            side_effect=jwt.PyJWKClientError("unavailable"),
        ):
            self.assertIsNone(await self.verifier.verify_token(self.token()))
