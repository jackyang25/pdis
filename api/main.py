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

from api.routes import chunker, configs, evidence, pd_reviewer

app = FastAPI(title="PDIS API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(configs.router, prefix="/api/configs", tags=["configs"])
app.include_router(chunker.router, prefix="/api/chunker", tags=["chunker"])
app.include_router(evidence.router, prefix="/api/evidence", tags=["evidence"])
app.include_router(pd_reviewer.router, prefix="/api/pd-reviewer", tags=["pd_reviewer"])


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
