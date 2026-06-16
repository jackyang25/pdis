# PDIS — Product Development Intelligence System

Layered system for developing Target Product Profiles (TPPs) faster and
with better grounding. Documents become structured blocks, rubric grades,
and monitor signals.

## Architecture

```
web/ (Next.js + shadcn/ui)  →  api/ (FastAPI)  →  services/  →  data/
                                                  shared/ (cross-cutting)
```

Imports flow one way only: `web/` -> `api/` -> `services/`.
Services import from each other only through `__init__.py` public
contracts.

Cross-cutting files live in `shared/`: `openai_client.py`,
`indications.yaml`, and `attributes.yaml`.

## Services

| Folder | UI name | One-line job | Depends on |
|---|---|---|---|
| `services/chunker/` | Chunker | Parse documents into ordered, citable `ContentBlock`s; optionally label sections. | — |
| `services/reviewer/` | Reviewer | Grade a document against a rubric on completeness and adherence. | chunker |
| `services/searcher/` | Searcher | Query -> source-attributed `Finding`s via OpenAI web search. | shared/openai_client |
| `services/monitor/` | Monitor | Files + 4 primitives -> drift `Match` records and evidence assessments over shared TPP attributes. | chunker, searcher |

Each service has its own README with the file map and public contract.

## Required inputs

Document tools use the same four primitives, picked once in the sidebar:

| Field | Purpose |
|---|---|
| `org` | Publisher of the source document (e.g., bmgf, who) |
| `source_type` | Document format (tpp, ppc, paper, ...) |
| `intervention_class` | Product class (vaccine, drug, diagnostic, device) |
| `indication` | Disease scope (malaria, rsv, ...) |

The first three select configs where applicable. All four are stamped on
document-derived outputs. Searcher is query-based and does not use these
document headers.

## Configs and vocabularies

Human-maintained domain content lives in YAML.

| Surface | Filename | Role |
|---|---|---|
| chunker configs | `services/chunker/configs/{org}_{source_type}_{intervention}.yaml` | Section taxonomy per document format |
| reviewer configs | `services/reviewer/configs/{org}_{source_type}_{intervention}.yaml` | Rubric per document format |
| monitor configs | `services/monitor/configs/{org}_{source_type}_{intervention}.yaml` | Query-generation tuning |
| shared indications | `shared/indications.yaml` | Indication vocabulary per intervention |
| shared attributes | `shared/attributes.yaml` | TPP attribute vocabulary per intervention |

Add a new `(org × source_type × intervention)` by dropping YAMLs into
the matching `configs/` folders. No code changes are needed for ordinary
domain additions.

## Repository layout

```
pdis/
  shared/
    openai_client.py
    indications.yaml
    attributes.yaml
  services/
    chunker/
    reviewer/
    searcher/
    monitor/
  api/
    main.py
    routes/
    schemas.py
    deps.py
    streaming.py
  web/
    app/                 routes: /chunker, /reviewer, /searcher, /monitor
    components/
    lib/
  data/
```

## Design rules

1. **One config per domain change.** Adding an `(org × source_type × intervention)` is YAML only.
2. **Services are stateless.** Same input -> same output, modulo LLM/web drift.
3. **Cross-service calls go through `__init__.py`.** No reaching into `stages/` or internals.
4. **Code = infrastructure, config = domain content.** Domain rubric/query content lives in YAML.
5. **Single provider.** All services share `shared/openai_client.py`.

## Running locally

Two processes: FastAPI gateway and Next.js dev server.

```bash
# Backend
source .venv/bin/activate
pip install -r api/requirements.txt
cp .env.example .env   # set OPENAI_API_KEY
python -m uvicorn api.main:app --reload --port 8000

# Frontend
cd web
npm install
npm run dev          # http://localhost:3000
```

The frontend calls the gateway at `http://localhost:8000`. API keys are
read server-side from `.env`; the browser never sees them.
