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

from api.routes import assistant, chunker, configs, scout, reviewer, searcher

app = FastAPI(title="PDIS API", version="0.1.0")

# Allowed browser origins. Comma-separated env var for deploys; defaults to
# local dev. e.g. CORS_ALLOW_ORIGINS="https://pdis-web.onrender.com"
_origins = os.getenv("CORS_ALLOW_ORIGINS", "http://localhost:3000")
allow_origins = [o.strip() for o in _origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(configs.router, prefix="/api/configs", tags=["configs"])
app.include_router(chunker.router, prefix="/api/chunker", tags=["chunker"])
app.include_router(reviewer.router, prefix="/api/reviewer", tags=["reviewer"])
app.include_router(searcher.router, prefix="/api/searcher", tags=["searcher"])
app.include_router(scout.router, prefix="/api/scout", tags=["scout"])
app.include_router(assistant.router, prefix="/api/assistant", tags=["assistant"])


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
