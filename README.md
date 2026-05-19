# PDIS — Product Development Intelligence System

PDIS is a layered system for developing Target Product Profiles (TPPs) faster and with better grounding. Documents become structured records, records become decisions.

The premise: TPP development is held back less by missing tools than by missing shared foundations. Documents are scattered, processing is redone per tool, evidence is implicit, and nothing persists across runs. PDIS fixes that by treating documents and evidence as first-class shared assets that any service can produce, query, or build on.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│ web/                         Next.js + shadcn/ui        │
└─────────────────────────────────────────────────────────┘
                          │ HTTP
                          ▼
┌─────────────────────────────────────────────────────────┐
│ api/                         FastAPI gateway            │
└─────────────────────────────────────────────────────────┘
                          │ imports
                          ▼
┌─────────────────────────────────────────────────────────┐
│ services/                    Processing services        │
│   chunker, evidence, pd_reviewer                        │
│   (each callable headlessly OR via the gateway OR by    │
│    other services; deployable independently)            │
└─────────────────────────────────────────────────────────┘
                          │ reads/writes
                          ▼
┌─────────────────────────────────────────────────────────┐
│ data/                        Local store (mimics EDP)   │
└─────────────────────────────────────────────────────────┘

Cross-cutting:  llm_client.py  (shared SDK)
```

Each service has the same shape: a stateless pipeline, a CLI for headless invocation, and a route in `api/`. In production, each service becomes an independently deployable container; today they're Python packages in this monorepo, fronted by one FastAPI gateway and one Next.js frontend.

## Services

| Service | Status | One-line job | Dependencies |
|---|---|---|---|
| `services/chunker/` | shipped | Parse documents (`.docx`, `.pdf`) into ordered, citable `ContentBlock`s; optionally label sections. | none |
| `services/evidence/` | shipped | Documents → source-backed `Claim`s (extract → bind → appraise). | chunker |
| `services/pd_reviewer/` | shipped | Grade a document against a TPP rubric. Optionally consumes evidence claims as peer benchmark. | chunker, evidence (optional) |
| `services/pd_watch/` | planned | Temporal change detection over a persistent claim store. | evidence + persistent store |
| `services/pd_gate_assembler/` | planned | Assemble a stage-gate packet from claims + reviews. | evidence + pd_reviewer |

Each service has a README inside its folder with its own contract, file map, and run instructions.

## Now vs. Later

Each service has two operating modes. The code is the same; the **trigger** and the **storage** differ. Work built against today's mode carries forward unchanged.

| Service | Now (manual, stateless) | Later (autonomous, persistent) | What stays the same |
|---|---|---|---|
| chunker | User uploads doc → blocks returned to caller | Scheduled/event-driven ingest → blocks passed downstream | Pipeline, `ContentBlock` schema, configs |
| evidence | User runs extractor → claims as JSONL in `data/evidence_table/` | Connectors extract on new docs → claims upserted to Delta on EDP | `Claim` schema, extractor logic, `ClaimsStore` Protocol |
| pd_reviewer | User uploads target doc → graded against peer claims in folder | User or job submits doc → graded against peer claims in Delta | Pipeline, rubric configs, peer-benchmarking logic |
| pd_watch | — (requires history) | Diffs claims across time, surfaces material change | n/a today |

**The bridge:** services consume `ClaimsStore` through a Protocol. Today it reads JSONLs; tomorrow it reads Delta. No service-side code changes.

**Deferred (waiting on persistent substrate):** autonomous ingestion, dedup, cross-time diffs, multi-user collaboration, recency-based decay.

**Not deferred (builds value either side of the bridge):** the `Claim` schema, extractors, rubric configs, and the manual corpus you seed today. Every claim produced now is one the autonomous pipeline would have produced — just slower. When the substrate lands, the hand-built corpus becomes the seed dataset, not throwaway work.

## Deployment Model

**Today: one bundle.** PDIS ships as one Next.js frontend, one FastAPI gateway, and `services/` imported as local Python packages. Two processes on one machine, one `data/` volume. Right call for 1–N users, no autonomous ingestion, fast iteration.

**Later: decoupled.** Each service becomes its own container / job, exposed over HTTP or gRPC. The Next.js frontend calls services through what is already the gateway pattern today. `data/` is replaced by Delta on EDP, shared across services.

**Why the split is mechanical, not architectural:** services already talk to each other only through their `__init__.py` public contract, and `api/` already wraps them as HTTP routes. The Python boundary today becomes the network boundary tomorrow — same shape, different transport. Statelessness, the `ClaimsStore` Protocol, and one-direction imports (`web/` → `api/` → `services/`, never the reverse) make the eventual decouple a packaging change rather than a rewrite.

## How Services Interact

Services call each other through **public contracts** declared in `__init__.py`. They never reach into another service's internals (`stages/`, helpers). This mirrors how separate deployments would interact — over a public API surface, not by sharing implementation code.

- **chunker** has no dependencies. It's the root.
- **evidence** calls `chunker.run_pipeline` to get parsed blocks, then extracts/binds/appraises claims.
- **pd_reviewer** calls `chunker.run_pipeline` for parsed + labeled blocks, then grades. Optionally calls `evidence.FileClaimsStore` to read accumulated claims as additional grading signal.

Every service is **stateless**: same input → same output (modulo small LLM drift). No service writes to a persistent store in the active path — outputs are returned to the caller (CLI writes files, UI shows + offers downloads).

## What Counts As Evidence

A `Claim` must satisfy three properties:

1. **Source-backed** — traceable to a specific source (paper, trial, interview, market report, regulatory doc, model run, expert note, real-world data, TPP document).
2. **Atomic** — one assertion per claim. Paragraphs defeat `diff`, `contradictions`, and `coverage`.
3. **Decision-relevant** — could support, challenge, or revise a TPP attribute, threshold, or scope choice.

Expert opinion counts as evidence when attributed and labeled honestly. Unsourced inherited assumptions do not. See `services/evidence/README.md` for the full claim schema.

## External Capabilities Outside The Substrate

Some evidence sources are heavy capabilities with their own lifecycles. They live outside the substrate and feed findings in as `Claim`s via source-specific extractors:

- **Biomedical knowledge graphs** (OpenTargets, MONDO, ClinicalTrials.gov, etc.): selectively ingested with `source_kind=knowledge_graph`.
- **WHO PPCs, TPPs, and peer-org product profiles** (FIND, CEPI, MMV, DNDi, etc.): downloaded, chunked, then mined into claims with `source_kind=product_profile`.
- **Causal / EHR-backed modeling** (PyWhy, OHDSI, partner platforms): model runs emit claims with `claim_type=modelled_impact` and `source_kind=model_run`.

In each case, the substrate ingests **findings**, not engines or raw datasets. This keeps the substrate from collapsing into "the place where all data lives."

## Design Rules

These are load-bearing. Violations create overlap and force rewrites.

1. **PD-specific logic never enters service infrastructure.** Domain enters through injected configs (`DocumentTypeConfig`, `AttributeConfig`, `ReviewConfig`).
2. **Services are stateless.** Same input → same output (modulo small LLM drift). No persistence in the active path. Persistence is a deferred consumer.
3. **One writer per asset (when persistence lands).** Each service owns its output namespace; no service overwrites another's records.
4. **Services consume each other only through public contracts.** No reaching into `stages/`, helpers, or other internals. Cross-service calls go through the package root.
5. **One claim = one assertion.** Atomicity is what makes downstream comparison and filtering real.
6. **Provenance is required.** No source, no claim.
7. **Labels, not gatekeeping.** Weak evidence is stored and labeled weak; consumers decide weight.
8. **Re-ingestion is a full rewrite per `source_id`.** Services never edit existing records; human curation lives in a separate, non-cascading table.

## Repository Layout

```
pdis/
  llm_client.py          shared SDK — LLM provider abstraction (Anthropic, OpenAI)
  services/              processing services; each independently deployable in production
    chunker/             documents (.docx, .pdf) → ContentBlocks (+ section labels)
    evidence/            documents → Claims (extract → bind → appraise)
    pd_reviewer/         grade a document against a TPP rubric
  api/                   FastAPI gateway — wraps services as HTTP routes
    main.py              entry point: `uvicorn api.main:app --reload`
    routes/              per-service routes (chunker, evidence, pd_reviewer, configs)
    schemas.py           Pydantic response models (wire contract)
    deps.py              LLM client construction from env
  web/                   Next.js frontend (shadcn/ui + Tailwind)
    app/                 routes: /, /chunker, /evidence, /pd-reviewer
    components/          shared UI primitives + tool-specific panels
    lib/                 api client + header store
  data/                  local data store (gitignored); mimics EDP for now
    evidence_table/      drop claims.jsonl files here to query across runs
```

Layer rules:

- **`services/`** — independently deployable processing services. In production, each runs as a worker / Lambda / DAG step.
- **`api/`** — thin HTTP gateway over services. Consumes service public contracts; never imported by them.
- **`web/`** — user-facing Next.js UI. Talks only to `api/` over HTTP.
- **`data/`** — local mimic of EDP / Delta. Where claims accumulate. The interface stays the same when the real substrate lands.
- **`llm_client.py`** — shared SDK. Used by all services.

Cross-layer imports follow one direction: `web/` → `api/` → `services/`; services depend on each other only through public contracts (`__init__.py`), never the reverse.

## Running locally

Two processes: the API gateway and the Next.js dev server.

```bash
# 1. Backend (Python 3.11+, virtualenv recommended)
pip install -r api/requirements.txt
# install service deps (chunker, evidence, pd_reviewer) per their own requirements.txt
export ANTHROPIC_API_KEY=sk-...   # or OPENAI_API_KEY
uvicorn api.main:app --reload --port 8000

# 2. Frontend (Node 18+)
cd web
npm install
cp .env.local.example .env.local
npm run dev   # http://localhost:3000
```

The Next.js dev server proxies `/api/*` to the FastAPI gateway via `next.config.mjs`. API keys are read server-side from the environment; the browser never sees them.

## Where To Start

- **New to the system** → read this file, then `services/chunker/README.md`, then `services/evidence/README.md`.
- **Adding a new (org × source_type × intervention)** → write the matching YAML in each service's `configs/` (`{org}_{source_type}_{intervention}.yaml` for chunker / pd_reviewer; `{intervention}.yaml` for evidence). No code changes.
- **Adding a new evidence extractor** → add `services/evidence/stages/extractor_<source_kind>.py` that emits `Claim` records. Register it in `EXTRACTORS`. No other service changes.
- **Adding a new service** → create `services/<name>/` with `__init__.py` declaring the public contract, plus `pipeline.py` + `cli.py` adapters. Consume upstream services via their public contracts.
