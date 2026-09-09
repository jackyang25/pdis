import json
import asyncio
import os
import subprocess
import sys
import threading
import time
import unittest
from contextlib import asynccontextmanager
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from mcp import Client
from mcp.server.auth.provider import AccessToken

from api import execution
from api.cors import GatewayCORSMiddleware
from api.mcp.server import create_mcp_app, create_server
from api.mcp.settings import MCPSettings
from api.schemas import SearcherRunResponse
from api.routes import searcher as searcher_route
from services.searcher import SearchReport, SearchRuntime


class MCPToolsTests(unittest.IsolatedAsyncioTestCase):
    async def test_worker_progress_reaches_the_mcp_client_in_order(self):
        events = []

        async def received(progress, total, message):
            events.append((progress, message))

        def execute(prepared, progress):
            progress("searching", 1, 2)
            progress("searching", 2, 2)
            return SearcherRunResponse(query="malaria", findings=[])

        with (
            patch("api.operations.searcher.prepare_search"),
            patch("api.operations.searcher.execute_search", side_effect=execute),
        ):
            async with Client(create_server()) as client:
                result = await client.call_tool(
                    "searcher_search",
                    {"request": {"query": "malaria"}},
                    progress_callback=received,
                )
        self.assertFalse(result.is_error)
        self.assertEqual(events, [(1, "searching: 1/2"), (2, "searching: 2/2")])

    async def test_cancelled_caller_does_not_free_running_workers_capacity(self):
        from api.mcp.execution import call_operation
        from unittest.mock import AsyncMock

        entered, release, finished = (
            threading.Event(),
            threading.Event(),
            threading.Event(),
        )

        def work(progress):
            entered.set()
            try:
                release.wait(timeout=5)
                return SearcherRunResponse(query="test", findings=[])
            finally:
                finished.set()

        with patch.object(execution, "_run_slots", threading.Semaphore(1)):
            task = asyncio.create_task(
                call_operation(work, AsyncMock(), uses_capacity=True)
            )
            try:
                self.assertTrue(await asyncio.to_thread(entered.wait, 2))
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
                with self.assertRaises(execution.CapacityExceeded):
                    with execution.run_slot(wait=False):
                        pass
            finally:
                release.set()
                self.assertTrue(await asyncio.to_thread(finished.wait, 2))

    async def test_discovery_and_search_use_structured_contract(self):
        server = create_server()
        expected = SearcherRunResponse(query="malaria", findings=[], lanes=[])
        with (
            patch("api.operations.searcher.prepare_search") as prepare,
            patch(
                "api.operations.searcher.execute_search", return_value=expected
            ) as execute,
        ):
            async with Client(server) as client:
                tools = await client.list_tools()
                self.assertEqual(
                    {tool.name for tool in tools.tools},
                    {"searcher_sources", "searcher_search"},
                )
                tool = next(t for t in tools.tools if t.name == "searcher_search")
                self.assertIsNotNone(tool.output_schema)
                result = await client.call_tool(
                    "searcher_search",
                    {"request": {"query": "malaria", "sources": ["pubmed"]}},
                )
                self.assertFalse(result.is_error)
                self.assertEqual(result.structured_content, expected.model_dump())
                self.assertEqual(prepare.call_args.args[0].sources, ["pubmed"])
                execute.assert_called_once()

    async def test_busy_and_provider_errors_are_not_findings(self):
        with (
            patch.object(execution, "_run_slots", threading.Semaphore(0)),
            patch("api.operations.searcher.prepare_search") as prepare,
        ):
            async with Client(create_server()) as client:
                result = await client.call_tool(
                    "searcher_search", {"request": {"query": "malaria"}}
                )
                self.assertTrue(result.is_error)
                self.assertEqual(
                    result.structured_content["error"]["code"], "server_busy"
                )
                prepare.assert_not_called()
        with patch(
            "api.operations.searcher.prepare_search",
            side_effect=RuntimeError("secret provider credential"),
        ):
            async with Client(create_server()) as client:
                result = await client.call_tool(
                    "searcher_search", {"request": {"query": "malaria"}}
                )
                self.assertTrue(result.is_error)
                self.assertNotIn("secret", str(result))


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.settings = MCPSettings(
            url="https://pdis.example/api/mcp",
            issuer="https://id.example/",
            jwks_url="https://id.example/keys",
            audience="pdis",
            browser_origins=("https://client.example",),
        )

        class Verifier:
            async def verify_token(self, token):
                if token not in {"valid", "no-scope"}:
                    return None
                return AccessToken(
                    token=token,
                    client_id="test",
                    subject="employee",
                    scopes=["pdis:search"] if token == "valid" else [],
                    expires_at=int(time.time()) + 60,
                    resource="https://pdis.example/api/mcp",
                )

        self.child = create_mcp_app(self.settings, token_verifier=Verifier())

        @asynccontextmanager
        async def lifespan(app):
            async with self.child.router.lifespan_context(self.child):
                yield

        self.app = FastAPI(lifespan=lifespan)
        self.app.add_middleware(
            GatewayCORSMiddleware,
            mcp_origins=self.settings.allowed_origins,
            allow_origins=[self.settings.origin],
            allow_methods=["*"],
            allow_headers=["*"],
        )
        self.app.include_router(searcher_route.router, prefix="/api/searcher")
        self.app.mount("/api", self.child)
        # TestClient owns the complete lifespan in one task, as ASGI servers do.
        self.client = TestClient(self.app, base_url="https://pdis.example")
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)

    def test_auth_challenge_points_to_reachable_metadata(self):
        response = self.client.post("/api/mcp", json={})
        self.assertEqual(response.status_code, 401)
        self.assertIn(self.settings.metadata_url, response.headers["www-authenticate"])
        metadata = self.client.get(self.settings.metadata_url)
        self.assertEqual(metadata.status_code, 200)
        self.assertEqual(metadata.json()["resource"], self.settings.url)
        self.assertEqual(
            metadata.json()["authorization_servers"], [self.settings.issuer]
        )

    def test_missing_scope_is_forbidden(self):
        response = self.client.post(
            "/api/mcp", json={}, headers={"Authorization": "Bearer no-scope"}
        )
        self.assertEqual(response.status_code, 403)

    def test_configured_browser_can_discover_auth_and_call_tools(self):
        headers = {"Origin": "https://client.example"}
        denied = self.client.post("/api/mcp", json={}, headers=headers)
        self.assertEqual(denied.status_code, 401)
        self.assertIn(
            "WWW-Authenticate", denied.headers["access-control-expose-headers"]
        )
        self.assertEqual(
            denied.headers["access-control-allow-origin"], "https://client.example"
        )
        response = self.client.post(
            "/api/mcp",
            json={"jsonrpc": "2.0", "id": 3, "method": "tools/list", "params": {}},
            headers={
                **headers,
                "Authorization": "Bearer valid",
                "Accept": "application/json, text/event-stream",
                "MCP-Protocol-Version": "2025-11-25",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("searcher_search", response.text)
        rejected = self.client.post(
            "/api/mcp",
            json={},
            headers={
                "Authorization": "Bearer valid",
                "Origin": "https://unknown.example",
            },
        )
        self.assertEqual(rejected.status_code, 403)

    def test_authenticated_protocol_initialization(self):
        response = self.client.post(
            "/api/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1"},
                },
            },
            headers={
                "Authorization": "Bearer valid",
                "Accept": "application/json, text/event-stream",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        messages = [
            json.loads(line[6:])
            for line in response.text.splitlines()
            if line.startswith("data: ")
        ]
        self.assertEqual(messages[0]["result"]["serverInfo"]["name"], "PDIS")

    def rpc(self, method, params):
        response = self.client.post(
            "/api/mcp",
            json={"jsonrpc": "2.0", "id": 2, "method": method, "params": params},
            headers={
                "Authorization": "Bearer valid",
                "Accept": "application/json, text/event-stream",
                "MCP-Protocol-Version": "2025-11-25",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        return next(
            json.loads(line[6:])
            for line in response.text.splitlines()
            if line.startswith("data: ")
        )

    def test_remote_discovery_and_http_mcp_result_parity(self):
        discovered = self.rpc("tools/list", {})["result"]["tools"]
        self.assertEqual(
            {t["name"] for t in discovered}, {"searcher_sources", "searcher_search"}
        )
        with (
            patch(
                "api.operations.searcher.get_search_runtime",
                return_value=SearchRuntime(llm_client=object()),
            ),
            patch(
                "api.operations.searcher.run_pipeline", return_value=SearchReport()
            ) as pipeline,
        ):
            remote = self.rpc(
                "tools/call",
                {
                    "name": "searcher_search",
                    "arguments": {
                        "request": {
                            "query": "  malaria  ",
                            "sources": ["pubmed"],
                            "condition": " malaria ",
                            "entities": [{"name": "BRAF", "entity_type": "gene"}],
                        }
                    },
                },
            )["result"]
            self.assertFalse(remote.get("isError", False), remote)
            web = self.client.post(
                "/api/searcher/run",
                data={
                    "query": "  malaria  ",
                    "sources": "pubmed",
                    "condition": " malaria ",
                    "entities": "BRAF:gene",
                },
            )
            self.assertEqual(web.status_code, 200)
            completed = next(
                json.loads(line)["result"]
                for line in web.text.splitlines()
                if json.loads(line)["event"] == "complete"
            )
            self.assertEqual(remote["structuredContent"], completed)
            self.assertEqual(pipeline.call_count, 2)
            self.assertEqual(pipeline.call_args.kwargs["condition"], "malaria")

    def test_invalid_remote_input_never_starts_operation(self):
        with patch("api.operations.searcher.prepare_search") as prepare:
            result = self.rpc(
                "tools/call",
                {
                    "name": "searcher_search",
                    "arguments": {
                        "request": {"query": " ", "provider": "caller-chosen"}
                    },
                },
            )
            self.assertTrue("error" in result or result["result"].get("isError"))
            prepare.assert_not_called()

    def test_remote_sources_match_http_sources(self):
        with patch("api.operations.searcher.get_search_integrations", return_value={}):
            remote = self.rpc(
                "tools/call", {"name": "searcher_sources", "arguments": {}}
            )["result"]
            web = self.client.get("/api/searcher/sources")
            self.assertEqual(remote["structuredContent"]["sources"], web.json())


class GatewayMountTests(unittest.TestCase):
    def test_main_app_mount_is_opt_in_without_changing_health(self):
        script = """
from fastapi.testclient import TestClient
from api.main import app
import json
with TestClient(app, base_url='https://pdis.example') as client:
    print(json.dumps([client.get('/api/health').status_code,
        client.post('/api/mcp', json={}).status_code,
        client.get('/api/.well-known/oauth-protected-resource').status_code]))
"""
        for enabled, expected in (
            ("false", [200, 404, 404]),
            ("true", [200, 401, 200]),
        ):
            with self.subTest(enabled=enabled):
                env = {
                    **os.environ,
                    "PDIS_MCP_ENABLED": enabled,
                    "PDIS_MCP_URL": "https://pdis.example/api/mcp",
                    "PDIS_MCP_ISSUER": "https://id.example/",
                    "PDIS_MCP_JWKS_URL": "https://id.example/keys",
                    "PDIS_MCP_AUDIENCE": "pdis",
                }
                process = subprocess.run(
                    [sys.executable, "-c", script],
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                self.assertEqual(process.returncode, 0, process.stderr)
                self.assertEqual(
                    json.loads(process.stdout.strip().splitlines()[-1]), expected
                )
