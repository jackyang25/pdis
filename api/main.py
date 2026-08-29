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

app = FastAPI(title="PDIS API", version="0.1.0")

def _cors_origins() -> list[str]:
    """Resolve explicit origins or Render-injected external hostnames."""
    explicit = os.getenv("CORS_ALLOW_ORIGINS", "").strip()
    if explicit:
        return [origin.strip() for origin in explicit.split(",") if origin.strip()]
    hosts = os.getenv("CORS_ALLOW_HOSTS", "").strip()
    if hosts:
        return [
            host if "://" in host else f"https://{host}"
            for host in (item.strip() for item in hosts.split(","))
            if host
        ]
    return ["http://localhost:3000"]


allow_origins = _cors_origins()

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
