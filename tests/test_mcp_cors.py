import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.responses import Response

from api.cors import GatewayCORSMiddleware


class CORSTests(unittest.TestCase):
    def test_mcp_browser_origin_does_not_open_existing_web_endpoints(self):
        app = FastAPI()
        app.add_middleware(
            GatewayCORSMiddleware,
            mcp_origins=["https://client.example"],
            allow_origins=["https://pdis.example"],
            allow_methods=["*"],
            allow_headers=["*"],
        )

        @app.get("/api/mcp")
        def denied():
            return Response(
                status_code=401,
                headers={
                    "WWW-Authenticate": 'Bearer resource_metadata="https://pdis.example/api/.well-known/oauth-protected-resource"'
                },
            )

        with TestClient(app) as client:
            preflight = {
                "Origin": "https://client.example",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,mcp-protocol-version",
            }
            self.assertEqual(
                client.options("/api/mcp", headers=preflight).status_code, 200
            )
            self.assertEqual(
                client.options("/api/searcher/run", headers=preflight).status_code, 400
            )
            challenge = client.get(
                "/api/mcp", headers={"Origin": "https://client.example"}
            )
            self.assertEqual(
                challenge.headers["access-control-allow-origin"],
                "https://client.example",
            )
            self.assertIn(
                "WWW-Authenticate", challenge.headers["access-control-expose-headers"]
            )
            unknown = client.options(
                "/api/mcp",
                headers={**preflight, "Origin": "https://unapproved.example"},
            )
            self.assertEqual(unknown.status_code, 400)
