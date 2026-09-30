"""One PDIS MCP server, mounted behind SDK auth under the existing /api ingress."""

from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from mcp.server import MCPServer
from mcp.server.auth.middleware.auth_context import AuthContextMiddleware
from mcp.server.auth.middleware.bearer_auth import (
    BearerAuthBackend,
    RequireAuthMiddleware,
)
from mcp.server.auth.provider import TokenVerifier
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import AnyHttpUrl
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.responses import JSONResponse
from starlette.routing import Route

from .auth import JWTVerifier
from .settings import MCPSettings, MCP_PATH, MCP_METADATA_PATH
from .tools import searcher


def _instructions(web_url: str | None) -> str:
    # Orientation only. Not every client shows server instructions to the model, so each
    # rule an agent must follow lives in the description of the tool it governs.
    lines = [
        "PDIS is the Gates Foundation's Product Development Intelligence Suite. Its tools "
        "retrieve external evidence for global-health product development.",
        "Start with searcher_sources, then searcher_search; each tool's description gives its rules.",
    ]
    if web_url:
        lines.append(f"The same search can be run in the PDIS web app at {web_url}/searcher.")
    return "\n".join(lines)


def create_server(web_url: str | None = None) -> MCPServer:
    """Protocol registrations only. Not a public, unauthenticated entry point.

    `web_url` is the PDIS web app's origin, so the agent can point a user to the page that
    runs the same search. Omitted where no public address is configured.
    """
    server = MCPServer(
        "PDIS",
        version="0.1.0",
        # Read once per session, before any tool description.
        instructions=_instructions(web_url),
    )
    searcher.register(server)
    return server


def create_mcp_app(
    settings: MCPSettings, *, token_verifier: TokenVerifier | None = None
) -> Starlette:
    public = urlsplit(settings.url)
    server = create_server(web_url=f"{public.scheme}://{public.netloc}")
    protocol = server.streamable_http_app(
        streamable_http_path=MCP_PATH.removeprefix("/api"),
        stateless_http=True,
        max_request_body_size=64 * 1024,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=[urlsplit(settings.url).netloc],
            allowed_origins=settings.allowed_origins,
        ),
    )
    protected = RequireAuthMiddleware(
        protocol,
        [settings.scope],
        AnyHttpUrl(settings.metadata_url),
    )

    async def metadata(request):
        return JSONResponse(
            {
                "resource": settings.url,
                "authorization_servers": [settings.issuer],
                "scopes_supported": [settings.scope],
                "bearer_methods_supported": ["header"],
            }
        )

    @asynccontextmanager
    async def lifespan(app):
        async with protocol.router.lifespan_context(protocol):
            yield

    # Compose the SDK's auth middleware explicitly so its challenge advertises a
    # metadata URL within /api. No root-level OAuth routes or ingress exceptions.
    return Starlette(
        routes=[
            Route(MCP_PATH.removeprefix("/api"), endpoint=protected),
            Route(MCP_METADATA_PATH.removeprefix("/api"), metadata, methods=["GET"]),
        ],
        middleware=[
            Middleware(
                AuthenticationMiddleware,
                backend=BearerAuthBackend(
                    token_verifier or JWTVerifier(settings),
                    resource_server_url=AnyHttpUrl(settings.url),
                ),
            ),
            Middleware(AuthContextMiddleware),
        ],
        lifespan=lifespan,
    )
