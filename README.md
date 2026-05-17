# PDIS — Product Development Intelligence System

PDIS is a layered system for developing Target Product Profiles (TPPs) faster and with better grounding. Documents become structured records, records become decisions, all stateless until a persistent store lands.

The premise: TPP development is held back less by missing tools than by missing shared foundations. Documents are scattered, processing is redone per tool, evidence is implicit, and nothing persists across runs. PDIS fixes that by treating documents and evidence as first-class shared assets that any service can produce, query, or build on.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│ dashboard/                   Streamlit UI surface       │
└─────────────────────────────────────────────────────────┘
                          │ calls
                          ▼
┌─────────────────────────────────────────────────────────┐
│ services/                    Processing services        │
│   chunker, evidence, pd_reviewer                        │
│   (each callable headlessly OR via dashboard OR by      │
│    other services; deployable independently)            │
└─────────────────────────────────────────────────────────┘
                          │ reads/writes
                          ▼
┌─────────────────────────────────────────────────────────┐
│ data/                        Local store (mimics EDP)   │
└─────────────────────────────────────────────────────────┘

Cross-cutting:  llm_client.py  (shared SDK)
```

Each service has the same shape: a stateless pipeline, a CLI for headless invocation, and a UI adapter in `dashboard/`. In production, each service becomes an independently deployable container; today they're Python packages in this monorepo.

## Services

| Service | Status | One-line job | Dependencies |
|---|---|---|---|
| `services/chunker/` | shipped | Parse documents (`.docx`, `.pdf`) into ordered, citable `ContentBlock`s; optionally label sections. | none |
| `services/evidence/` | shipped | Documents → source-backed `Claim`s (extract → bind → appraise). | chunker |
| `services/pd_reviewer/` | shipped | Grade a document against a TPP rubric. Stateless, point-in-time. | chunker, evidence (optional) |
| `services/pd_watch/` | planned | Temporal change detection over a persistent claim store. | evidence + persistent store |
| `services/pd_gate_assembler/` | planned | Assemble a stage-gate packet from claims + reviews. | evidence + pd_reviewer |

Each service has a README inside its folder with its own contract, file map, and run instructions.

## How Services Interact

Services call each other through **public contracts** declared in `__init__.py`. They never reach into another service's internals (`stages/`, helpers). This mirrors how separate deployments would interact — over a public API surface, not by sharing implementation code.

- **chunker** has no dependencies. It's the root.
- **evidence** calls `chunker.run_pipeline` to get parsed blocks, then extracts/binds/appraises claims.
- **pd_reviewer** calls `chunker.run_pipeline` to get parsed + labeled blocks, then grades. Optionally calls `evidence.FileClaimsStore` to read accumulated claims as additional grading signal.

Every service is **stateless** today: same input → same output (modulo small LLM drift). No service writes to a persistent store in the active path — outputs are returned to the caller (CLI writes files, UI shows + offers downloads).

## Statelessness Today, Persistence Later

A persistent store (Delta on Unity Catalog / EDP, with a curation layer) is a **deferred consumer** of these services. When it lands, it ingests service outputs the same way the CLI/UI does today; the services themselves don't change.

`services/pd_watch/` requires persistence (you can't diff without history), so it stays planned until the store exists.

## What Counts As Evidence

A `Claim` must satisfy three properties:

1. **Source-backed** — traceable to a specific source (paper, trial, interview, market report, regulatory doc, model run, expert note, real-world data, TPP document).
2. **Atomic** — one assertion per claim. Paragraphs defeat `diff`, `contradictions`, and `coverage`.
3. **Decision-relevant** — could support, challenge, or revise a TPP attribute, threshold, or scope choice.

Expert opinion counts as evidence when attributed and labeled honestly. Unsourced inherited assumptions do not. See `evidence/README.md` for the full claim schema.

## Storage (Deferred)

Today: no persistent substrate. Pipelines return their output to the caller; outputs are saved to CSV/JSONL via CLI or downloaded via UI.

Planned: a persistent substrate on Databricks / Unity Catalog ("EDP") as a deferred consumer of the pipelines. Specific table shapes, ownership, and curation mechanics will be designed when the work is scheduled.

## External Capabilities Outside The Substrate

Some evidence sources are heavy capabilities with their own lifecycles. They live outside the substrate and feed findings in as `Claim`s via source-specific extractors:

- **Biomedical knowledge graphs** (OpenTargets, MONDO, ClinicalTrials.gov, etc.): selectively ingested as claims with `source_kind=knowledge_graph`.
- **WHO PPCs, TPPs, and peer-org product profiles** (FIND, CEPI, MMV, DNDi, etc.): downloaded into `documents`, chunked, then mined into `claims` with `source_kind=product_profile`.
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

## Build Order

Bottom-up. Each service is shippable on its own; downstream services and apps grow against existing producers.

Shipped:

1. **Chunker** — `.docx` and `.pdf` parsers, mapper, configs, CLI, UI.
2. **Evidence** — Claim schema, `product_profile` extractor (LLM-based), binder, appraiser, stateless orchestrator, CLI, UI. Calls chunker via its public contract.
3. **PD Reviewer** — rubric grading on chunker output; optionally consumes evidence claims via `FileClaimsStore`. CLI, UI.

Next:

4. **More `AttributeConfig` YAMLs** (drug, diagnostic, device) and more chunker / pd_reviewer rubric configs per (org × source_type × intervention).
5. **Real persistence**: replace `FileClaimsStore` with a Delta-backed implementation against EDP — same interface, different substrate.
6. **`pd_watch`** — temporal change detection. Requires (5) to detect change.
7. **More evidence extractors** (paper, trial, knowledge_graph, model_run, …) — same `source_kind` dispatch shape.
8. **`pd_gate_assembler`** — stage-gate composition from claims + reviews.

## Repository Layout

```
pdis/
  llm_client.py          shared SDK — LLM provider abstraction (Anthropic, OpenAI)
  services/              processing services; each independently deployable in production
    chunker/             documents (.docx, .pdf) → ContentBlocks (+ section labels)
    evidence/            documents → Claims (extract → bind → appraise)
    pd_reviewer/         grade a document against a TPP rubric
  dashboard/             user-facing Streamlit UI surface over services
    app.py               entry point: `streamlit run dashboard/app.py`
    chunker_tool.py
    evidence_tool.py
    pd_reviewer_tool.py
    _ui.py               shared sidebar widgets
  data/                  local data store (gitignored); mimics EDP for now
    evidence_table/      drop claims.jsonl files here to query across runs
```

The layers mirror how a real distributed deployment is shaped:

- **`services/`** — independently deployable processing services. In production, each runs as a worker / Lambda / DAG step. Today, Python packages in this monorepo.
- **`dashboard/`** — UI surface. Only consumes services; never imported by them.
- **`data/`** — local mimic of EDP / Delta. Where claims accumulate. In production, replaced by a real persistent store; the interface stays the same.
- **`llm_client.py`** — shared SDK. Cross-cutting; used by all services. In production, becomes an internal package or a gateway-service client.

Each service has a **thin public contract** declared in its `__init__.py`. External consumers import from the package root only — never from `stages/`, `cli.py`, or other internals. Cross-layer imports follow one direction: `dashboard/` → `services/`, services depend on each other through public contracts, never the reverse.

## Where To Start

- New to the system → read this file, then `services/chunker/README.md`, then `services/evidence/README.md`.
- Adding a new (org × source_type × intervention) → write the matching YAML in each service's `configs/` (`{org}_{source_type}_{intervention}.yaml` for chunker / pd_reviewer; `{intervention}.yaml` for evidence). No code changes.
- Adding a new evidence extractor → add `services/evidence/stages/extractor_<source_kind>.py` that emits `Claim` records. Register it in `EXTRACTORS`. No other service changes.
- Adding a new service → create `services/<name>/` with `__init__.py` declaring the public contract, plus `pipeline.py` + `cli.py` adapters. Consume upstream services via their public contracts.

## Status Summary

| Capability | Status |
|---|---|
| Document parsing (.docx + .pdf) into ContentBlocks | shipped (chunker) |
| Section labeling via LLM | shipped (chunker mapper) |
| Chunker bundled export (CSV / JSONL) | shipped |
| TPP rubric grading | shipped (pd_reviewer) |
| Claim schema + AttributeConfig | shipped (evidence) |
| `product_profile` extractor | shipped (evidence) |
| Binder (LLM-driven attribute binding) | shipped (evidence) |
| Appraiser (heuristic strength + recency) | shipped (evidence) |
| Stateless evidence pipeline (UI + CLI) | shipped |
| Real `AttributeConfig` YAML for the active product class | in progress |
| pd_reviewer grounded in evidence claims | planned |
| Additional evidence extractors | planned |
| Persistent substrate on EDP | deferred |
| Curation layer | deferred |
| Temporal operations on the substrate | deferred |
| `pd_watch`, `pd_gate_assembler` | planned (require persistence) |
