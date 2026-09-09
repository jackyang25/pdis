"""Keep employee MCP browser clients separate from the web application's origins."""

from starlette.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

from api.mcp.settings import MCP_PATH, MCP_METADATA_PATH


class GatewayCORSMiddleware:
    def __init__(
        self, app: ASGIApp, *, mcp_origins: list[str] | None = None, **web_options
    ):
        self.web = CORSMiddleware(app, **web_options)
        self.mcp = CORSMiddleware(
            app,
            allow_origins=mcp_origins or [],
            allow_methods=["GET", "POST", "DELETE"],
            allow_headers=[
                "Authorization",
                "Content-Type",
                "Accept",
                "MCP-Protocol-Version",
                "Last-Event-ID",
            ],
            expose_headers=["WWW-Authenticate", "MCP-Protocol-Version", "X-Request-ID"],
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        handler = (
            self.mcp if scope.get("path") in {MCP_PATH, MCP_METADATA_PATH} else self.web
        )
        await handler(scope, receive, send)
