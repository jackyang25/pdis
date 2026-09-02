"""FastAPI gateway over PDIS services.

Each service is wrapped as a route group; the Next.js frontend talks to
this gateway only. Service public contracts (imports from `services/*`)
are the only surface this gateway calls into.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

import os

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
    archivist,
    assistant,
    chunker,
    configs,
    screener,
    inspector,
    scout,
    searcher,
)

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
)

def _cors_origins() -> list[str]:
    """Resolve explicit browser origins allowed to call this gateway.

    Deployments that serve the client and this gateway from one hostname make
    every browser call same-origin, so nothing here is consulted and no value
    needs to be set. The variable matters for split-origin deployments and for
    local development, where the client is on :3000 and this gateway on :8000.

    One variable, holding full origins. A second that took bare hostnames and
    assumed https existed to consume a hostname a platform injected; a
    deployment that sets both gets whichever this function reads first, which is
    not a thing a reader can see from either value.
    """
    explicit = os.getenv("CORS_ALLOW_ORIGINS", "").strip()
    if explicit:
        return [origin.strip() for origin in explicit.split(",") if origin.strip()]
    return ["http://localhost:3000"]


allow_origins = _cors_origins()

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # The generated ID is only useful to a caller that can read it back and
    # quote it in a bug report; a cross-origin response withholds every header
    # not named here.
    expose_headers=["X-Request-ID"],
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
app.include_router(archivist.router, prefix="/api/archivist", tags=["archivist"])
app.include_router(assistant.router, prefix="/api/assistant", tags=["assistant"])


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
