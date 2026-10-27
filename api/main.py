"""FastAPI gateway over PDIS services.

Each service is wrapped as a route group; the Next.js frontend talks to
this gateway only. Service public contracts (imports from `services/*`)
are the only surface this gateway calls into.
"""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi import FastAPI
from api.cors import GatewayCORSMiddleware

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


from api.deps import validate_configuration
from api.logging_config import RequestIdMiddleware, configure_logging

# Both run before the routers are imported, so a malformed setting stops the
# process here - naming the variable - rather than surfacing later as a default
# that silently replaced it, and so anything a service logs while importing is
# already formatted.
configure_logging()
validate_configuration()

from api.routes import (
    aligner,
    assistant,
    chunker,
    configs,
    drafter,
    screener,
    inspector,
    scout,
    searcher,
)
from api.mcp.server import create_mcp_app
from api.mcp.settings import load_mcp_settings

mcp_settings = load_mcp_settings()
mcp_app = create_mcp_app(mcp_settings) if mcp_settings else None


@asynccontextmanager
async def lifespan(app):
    if mcp_app is None:
        yield
    else:
        async with mcp_app.router.lifespan_context(mcp_app):
            yield

# Every route this gateway serves lives under `/api`, which is what lets one
# hostname carry both services: the ingress sends `/api/*` here and everything
# else to the Next.js client. FastAPI's own documentation endpoints default to
# `/docs`, `/redoc`, and `/openapi.json` - outside that prefix, so they would be
# routed to the client and 404. Moving them under `/api` keeps the whole backend
# addressable by a single prefix rule.
app = FastAPI(
    title="PDIS API",
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

#: Browser origins allowed to call this gateway across origins: the local client, on :3000
#: while the gateway is on :8000. A deployment serves both from one hostname, so its calls
#: are same-origin and need no entry. Never `*`: credentials are allowed, and Starlette
#: answers a credentialed request under `*` by echoing whatever origin asked.
LOCAL_CLIENT_ORIGINS = ["http://localhost:3000"]

app.add_middleware(
    GatewayCORSMiddleware,
    mcp_origins=mcp_settings.allowed_origins if mcp_settings else [],
    allow_origins=LOCAL_CLIENT_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # The generated ID is only useful to a caller that can read it back and
    # quote it in a bug report; a cross-origin response withholds every header
    # not named here. `Content-Disposition` carries the name a download is saved
    # under, which the server decides (Drafter's Word export).
    expose_headers=["X-Request-ID", "Content-Disposition"],
)

# Added after CORS, so it runs outside it: Starlette applies middleware in
# reverse registration order, and an ID assigned outside the CORS layer is set
# for the preflight rejection too, which is exactly the request you want to find
# in a log.
app.add_middleware(RequestIdMiddleware)

app.include_router(configs.router, prefix="/api/configs", tags=["configs"])
app.include_router(chunker.router, prefix="/api/chunker", tags=["chunker"])
app.include_router(aligner.router, prefix="/api/aligner", tags=["aligner"])
app.include_router(inspector.router, prefix="/api/inspector", tags=["inspector"])
app.include_router(screener.router, prefix="/api/screener", tags=["screener"])
app.include_router(searcher.router, prefix="/api/searcher", tags=["searcher"])
app.include_router(scout.router, prefix="/api/scout", tags=["scout"])
app.include_router(drafter.router, prefix="/api/drafter", tags=["drafter"])
app.include_router(assistant.router, prefix="/api/assistant", tags=["assistant"])


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


# Register last: existing HTTP routes keep their exact precedence and contracts.
# The child serves only /mcp and its advertised OAuth metadata route.
if mcp_app is not None:
    app.mount("/api", mcp_app)
