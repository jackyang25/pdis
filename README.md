# PDIS — Product Development Intelligence System

PDIS is a layered system for developing Target Product Profiles (TPPs) faster and with better grounding. It separates **the substrate** that produces and stores processed information from **the apps** that turn that information into decisions.

The premise: TPP development is held back less by missing tools than by missing shared foundations. Documents are scattered, processing is redone per tool, evidence is implicit, and nothing persists across runs. PDIS fixes that by treating documents and evidence as first-class shared assets, and treating each app as a thin consumer of those assets.

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│  APPS  (opinionated, PD-specific)                            │
│                                                              │
│   pd_reviewer          pd_watch          pd_gate_assembler   │
│   "is it good now?"    "what changed?"   "what should we     │
│                                            decide at the     │
│                                            gate?"            │
│                                                              │
├──────────────────────────────────────────────────────────────┤
│  EDP  (the substrate — Evidence & Document Platform)         │
│                                                              │
│   chunker              evidence                              │
│   documents → blocks   sources → claims                      │
│   (snapshot)           (live, temporal)                      │
│                                                              │
│   Storage: Delta tables in Unity Catalog (Databricks)        │
│   Shared: llm_client, schemas, export bundles                │
└──────────────────────────────────────────────────────────────┘
```

Two layers. Arrows go down only. Apps don't reach into each other's internals. The substrate has no opinion about PDs.

## Components

| Layer | Component | Status | One-line job |
|---|---|---|---|
| Substrate | `chunker/` | shipped | Parse TPP documents into ordered, citable `ContentBlock`s. |
| Substrate | `evidence/` | scaffold | Maintain a live, source-backed claim store bound to TPP attribute schemas. |
| App | `pd_reviewer/` | shipped | Grade a TPP against a rubric, grounded in evidence. Stateless, point-in-time. |
| App | `pd_watch/` | planned | Detect changes in evidence (or the TPP) that should trigger a revisit. Temporal. |
| App | `pd_gate_assembler/` | planned | Compose reviewer + watch + evidence snapshot into a decision-ready package for stage gates. Episodic. |

Each component has a README inside its folder with its own contract, file map, and run instructions.

## The Two-Layer Split

**Substrate (EDP)** owns the processed-data assets. It knows about documents, content blocks, sources, claims, attributes, and time. It knows nothing about TPPs — domain context enters through injected configs (`DocumentTypeConfig` for chunker, `AttributeSchema` for evidence).

**Apps** own the opinions. They know what "good" looks like, what to alert on, what a gate audience needs. They read from the substrate; they write only to their own artifact tables.

This split is what makes the system maintainable:

- Substrate moves slowly. Breaking changes are expensive. Contracts are stable.
- Apps move quickly. They evolve with TPP development practice.
- Substrate is reusable across domains. A non-TPP team could adopt EDP with their own schemas.
- Apps don't compete or overlap. Each has a distinct time shape, trigger, and audience.

## Data Flow

```
RAW                       PROCESSED (EDP)             CONSUMED (apps)
─────                     ─────────────────           ─────────────────
documents/    ──chunker──►  content_blocks   ──┐
                                                ├──► pd_reviewer  ──► reviews/
sources/      ──evidence─►  claims            ──┤
                            sources             ├──► pd_watch     ──► watch_events/
                            attribute_schemas ──┘
                                                 ──► pd_gate_assembler
                                                       (reads reviews + watch_events
                                                        + claims-as-of-gate)
                                                       ──► gate_packages/
```

Every asset has exactly one writer. Apps never write to substrate tables, never read from each other's internals.

## Snapshot vs. Live

The two substrate pipelines have different cadences, and the architecture treats them differently:

- **chunker** is **snapshot**. A document goes in, blocks come out. Same input → same output. Output is regenerable from the document; treat it as a cache.
- **evidence** is **live**. Claims accumulate over time, get revised, get superseded. The store is versioned and time-aware. Output is partly authored; treat it as a first-class asset.

Liveness is what makes pd_watch tractable. Without a temporal substrate, "what changed?" has no answer.

## What Counts As Evidence

A `Claim` must satisfy three properties:

1. **Source-backed** — traceable to a specific source (paper, trial, interview, market report, regulatory doc, model run, expert note, real-world data, TPP document).
2. **Atomic** — one assertion per claim. Paragraphs defeat `diff`, `contradictions`, and `coverage`.
3. **Decision-relevant** — could support, challenge, or revise a TPP attribute, threshold, or scope choice.

Expert opinion counts as evidence when attributed and labeled honestly. Unsourced inherited assumptions do not. See `evidence/README.md` for the full claim schema.

## Storage

EDP is deployed on Databricks. Unity Catalog provides governance, lineage, access control, and time travel. Delta tables are the public contract between substrate and apps.

| Table | Owner | Written by | Read by |
|---|---|---|---|
| `documents` | EDP | document ingestion | chunker, all apps |
| `content_blocks` | EDP | chunker | evidence (when source is a TPP), all apps |
| `sources` | EDP | evidence | all apps |
| `claims` | EDP | evidence pipelines | all apps |
| `attribute_schemas` | EDP | evidence | all apps |
| `reviews` | pd_reviewer | pd_reviewer | pd_watch, pd_gate_assembler |
| `watch_events` | pd_watch | pd_watch | pd_gate_assembler |
| `gate_packages` | pd_gate_assembler | pd_gate_assembler | leadership / external |

Apps consume substrate tables read-only via a thin SDK (`edp_client`) or direct Delta reads. Apps may run inside or outside Databricks; the contract is the table schema plus the SDK.

## External Capabilities Outside EDP

Some evidence sources are heavy capabilities with their own lifecycles. They live outside EDP and emit findings into `claims` via small extractors:

- **Biomedical knowledge graphs** (OpenTargets, MONDO, ClinicalTrials.gov, etc.): selectively ingested as claims with `source_type=knowledge_graph`.
- **WHO PPCs, TPPs, and peer-org product profiles** (FIND, CEPI, MMV, DNDi, etc.): downloaded into `documents`, chunked, then mined into `claims` with `source_type=product_profile`.
- **Causal / EHR-backed modeling** (PyWhy, OHDSI, partner platforms): model runs emit claims with `claim_type=modelled_impact` and `source_type=model_run`.

In each case, the substrate ingests **findings**, not engines or raw datasets. This keeps EDP from collapsing into "the place where all data lives."

## Design Rules

These are load-bearing. Violations create overlap and force rewrites.

1. **PD-specific logic never enters the substrate.** Domain enters through injected schemas.
2. **One writer per asset.** Substrate tables are written only by substrate pipelines; app tables only by their owning app.
3. **Apps don't read each other's internals.** They consume published outputs (other app tables or substrate tables).
4. **One claim = one assertion.** Atomicity is what makes the engine's operations real.
5. **Provenance is required.** No source, no claim.
6. **Labels, not gatekeeping.** Weak evidence is stored and labeled weak; consumers decide weight.
7. **Versioned, never mutated.** Revisions add versions; old versions remain queryable.
8. **Stateful only where stated.** Chunker is stateless. Evidence's store is the only stateful substrate piece. Apps are stateless except for their own artifact tables.

## Build Order

The system is built bottom-up. Each layer is shippable on its own; apps grow against an existing substrate.

1. **Document store** (centralize TPPs in Unity Catalog).
2. **Chunker as pipeline** (already exists as code; materialize `content_blocks` on ingest).
3. **Evidence MVP** (Claim schema, one AttributeSchema, ~30 hand-authored claims, minimal read path).
4. **pd_reviewer grounding** (optional read from `claims` to surface evidence behind attributes).
5. **First evidence extractor** (papers).
6. **Versioning, diff, contradictions, coverage on claims store.**
7. **pd_watch** (consumes `diff`).
8. **pd_gate_assembler** (composes reviewer + watch + evidence snapshot).
9. **Additional extractors** (KG, WHO corpus, model_run).
10. **Curation UI, source registry, run-manifest format.**

Earlier steps must not anticipate later ones beyond reserving fields in the schema. The chunker proved this pattern: `ContentBlock` reserved `section_label` and `label_confidence` from day one, so the mapper landed without migration. Evidence applies the same template.

## Repository Layout

```
pdis/
  chunker/             substrate — document parsing & mapping pipeline
  evidence/            substrate — claim extraction, binding, storage (scaffold)
  pd_reviewer/         app — TPP grading
  pd_watch/            app — temporal change detection (planned)
  pd_gate_assembler/   app — stage-gate decision packaging (planned)
  app.py               top-level Streamlit entry (legacy / shared shell)
```

Each folder has its own README, requirements, and configs. Substrate folders should never import from app folders. Apps may import substrate packages.

## Where To Start

- New to the system → read this file, then `chunker/README.md`, then `evidence/README.md`.
- Adding a new TPP family → write an `AttributeSchema` YAML and a chunker `DocumentTypeConfig` YAML. No code changes in the substrate.
- Adding a new evidence source → write an extractor under `evidence/extractors/` that emits `Claim` records. No substrate changes.
- Adding a new app → create a sibling folder. Consume substrate via the documented contract. Do not modify substrate to fit the app.

## Status Summary

| Capability | Status |
|---|---|
| Document parsing into ContentBlocks | shipped (chunker) |
| Section labeling via LLM | shipped (chunker mapper) |
| Export bundles for downstream ingestion | shipped (chunker) |
| TPP rubric grading | shipped (pd_reviewer) |
| Centralized document store on Databricks | in progress |
| Claim schema & AttributeSchema | scaffolded (evidence) |
| Live claim store with versioning | planned |
| Temporal queries (`diff`, `contradictions`) | planned |
| pd_watch | planned |
| pd_gate_assembler | planned |
| Evidence extractors (paper, KG, TPP corpus, model_run) | planned |
| Claim curation UI | planned |
