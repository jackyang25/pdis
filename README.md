# PDIS — Product Development Intelligence System

Layered system for developing Target Product Profiles (TPPs) faster and with better grounding. Documents become structured records; records become decisions.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│ web/                Next.js + shadcn/ui                 │
└─────────────────────────────────────────────────────────┘
                       │ HTTP
                       ▼
┌─────────────────────────────────────────────────────────┐
│ api/                FastAPI gateway                     │
└─────────────────────────────────────────────────────────┘
                       │ imports public contracts
                       ▼
┌─────────────────────────────────────────────────────────┐
│ services/           Processing services                 │
│   chunker, benchmarker, reviewer, searcher              │
└─────────────────────────────────────────────────────────┘
                       │ reads/writes
                       ▼
┌─────────────────────────────────────────────────────────┐
│ data/               Local claim store (mimics EDP)      │
└─────────────────────────────────────────────────────────┘

Cross-cutting:  shared/  (openai_client.py, anthropic_client.py, indications.yaml)
```

Imports flow one way only: `web/` → `api/` → `services/`. Services never import from `api/` or `web/`. Services import from each other only through `__init__.py` public contracts.

## Services

| Folder | UI name | One-line job | Depends on |
|---|---|---|---|
| `services/chunker/` | Chunker | Parse documents into ordered, citable `ContentBlock`s; optionally label sections. | — |
| `services/benchmarker/` | Benchmarker | Documents → source-backed `Claim`s bound to an attribute namespace. Builds the peer corpus. | chunker |
| `services/reviewer/` | Reviewer | Grade a document against a rubric on three dimensions (completeness, adherence, expertise). | chunker, benchmarker |
| `services/searcher/` | — (library-only) | Query → source-attributed `Finding`s via Anthropic web search. | shared/anthropic_client |

Each service has its own README with the file map and public contract.

## Required inputs (consistent across document tools)

Chunker, Benchmarker, and Reviewer require the same four primitives, picked once in the sidebar:

| Field | Purpose |
|---|---|
| `org` | Publisher of the source document (e.g., bmgf, who) |
| `source_type` | Document format (tpp, ppc, paper, …) |
| `intervention_class` | Product class (vaccine, drug, diagnostic, device) |
| `indication` | Disease scope (malaria, rsv, …) |

The first three select the config. All four are stamped on every document-derived output so downstream tools can filter (e.g., Reviewer pulls peer claims scoped to the same indication). Searcher is query-based and does not use these document headers.

## Configs

Configs are the only place a human edits domain content. Code stays stable.

| Service | Filename | Keyed by |
|---|---|---|
| chunker | `{org}_{source_type}_{intervention}.yaml` | full triple — sections per document format |
| benchmarker | `{intervention}.yaml` | intervention only — attribute namespace per product class |
| reviewer | `{org}_{source_type}_{intervention}.yaml` | full triple — rubric per document format |

Add a new (org × source_type × intervention) by dropping YAMLs into the matching `configs/` folders. No code changes.
Searcher has no configs; add one only when a real consumer needs domain keying.

## Repository layout

```
pdis/
  shared/                cross-cutting (not owned by any service)
    openai_client.py     OpenAI client (chunker/benchmarker/reviewer)
    anthropic_client.py  Anthropic client (searcher)
    indications.yaml     controlled vocabulary of indications per intervention
  services/              processing services
    chunker/             documents → ContentBlocks
    benchmarker/         documents → Claims (peer corpus)
    reviewer/            documents → graded ReviewResult
    searcher/            queries → Findings
  api/                   FastAPI gateway
    main.py              app
    routes/              per-service routes + configs
    schemas.py           Pydantic wire models
    deps.py              LLM client from env
    streaming.py         NDJSON streaming helper
  web/                   Next.js frontend
    app/                 routes: /chunker, /benchmarker, /reviewer
    components/          UI primitives + tool panels
    lib/                 API client + header store
  data/                  local claim store (gitignored); mimics EDP
    claims/              drop claims.jsonl files here
```

## Now vs. Later

Each service has two modes. Code is the same; trigger and storage differ. Work built today carries forward.

| Service | Now (manual) | Later (autonomous) | Stable interface |
|---|---|---|---|
| chunker | User uploads doc → blocks returned | Cron / event → blocks downstream | `ContentBlock`, configs |
| benchmarker | User extracts → JSONL in `data/claims/` | Connectors → `upsert_claims` on Delta | `Claim`, `ClaimsStore` Protocol |
| reviewer | User uploads draft → graded against folder | Same, but corpus lives in Delta | rubric configs, three-dimension grade shape |
| searcher | Python caller runs query → findings returned | Monitoring service consumes findings | `Finding`, `SearcherLLMClientProtocol` |

`ClaimsStore` is the bridge: today `FileClaimsStore` reads a folder, tomorrow `DeltaClaimsStore` reads a table. Service code doesn't change.

## Design rules

1. **One config per domain change.** Adding a (org × source_type × intervention) is YAML only.
2. **Services are stateless.** Same input → same output (modulo LLM drift). No persistence in the active path.
3. **Cross-service calls go through `__init__.py`.** No reaching into `stages/` or internals.
4. **One claim = one assertion.** Atomicity is what makes downstream filtering real.
5. **Provenance is required.** Every claim has a `source_id`, `source_locator`, and the header.
6. **Re-ingestion is a full rewrite per `source_id`.** Services never edit existing records.
7. **One shared client per provider.** `OpenAIClient` serves chunker/benchmarker/reviewer; `AnthropicClient` serves searcher.

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

The frontend calls the gateway at `http://localhost:8000`. API keys are read server-side from `.env`; the browser never sees them.

## Where to start

- **Add a new (org × source_type × intervention)** → drop matching YAMLs into each service's `configs/`. No code changes.
- **Add a new benchmarker extractor** (e.g., for `source_kind=paper`) → add `services/benchmarker/stages/extractor_paper.py`, register it in `EXTRACTORS`.
- **Add a new service** → create `services/<name>/` with `__init__.py` declaring the public contract.
