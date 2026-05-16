# PDIS — Product Development Intelligence System

PDIS is a layered system for developing Target Product Profiles (TPPs) faster and with better grounding. It separates **the substrate** that produces and stores processed information from **the apps** that turn that information into decisions.

The premise: TPP development is held back less by missing tools than by missing shared foundations. Documents are scattered, processing is redone per tool, evidence is implicit, and nothing persists across runs. PDIS fixes that by treating documents and evidence as first-class shared assets, and treating each app as a thin consumer of those assets.

## Architecture

Two layers. Apps consume substrate output; substrate never imports app code.

**Apps** (opinionated, PD-specific):

| Component | Question it answers |
|---|---|
| `pd_reviewer` | Is this PD good *now*? |
| `pd_watch` | What changed? *(planned, requires persistence)* |
| `pd_gate_assembler` | What should we decide at the gate? *(planned)* |

**Substrate** (shared, domain-agnostic):

| Component | Transformation |
|---|---|
| `chunker` | documents → `ContentBlock`s |
| `evidence` | `ContentBlock`s → `Claim`s (via extract → bind → appraise) |

Both substrate pipelines are stateless today: same input → same output, no persistence in the active path. Persistence (Delta tables in Unity Catalog on EDP) is a deferred consumer of the pipelines.

## Components

| Layer | Component | Status | One-line job |
|---|---|---|---|
| Substrate | `chunker/` | shipped | Parse documents (`.docx`, `.pdf`) into ordered, citable `ContentBlock`s. |
| Substrate | `evidence/` | shipped | Stateless pipeline: `ContentBlock`s → source-backed `Claim`s bound to an `AttributeConfig`. |
| App | `pd_reviewer/` | shipped | Grade a TPP against a rubric. Stateless, point-in-time. |
| App | `pd_watch/` | planned | Temporal app — depends on a persistent substrate. |
| App | `pd_gate_assembler/` | planned | Stage-gate composition app. |

Each component has a README inside its folder with its own contract, file map, and run instructions.

## The Two-Layer Split

**Substrate** owns the document → block → claim transformations. It knows about documents, content blocks, sources, claims, attributes. It knows nothing about TPPs — domain context enters through injected configs (`DocumentTypeConfig` for chunker, `AttributeConfig` for evidence).

**Apps** own the opinions. They know what "good" looks like, what to alert on, what a gate audience needs. They consume substrate output; they don't modify substrate internals.

This split is what makes the system maintainable:

- Substrate moves slowly. Breaking changes are expensive. Contracts are stable.
- Apps move quickly. They evolve with TPP development practice.
- Substrate is reusable across domains. A non-TPP team could adopt these pipelines with their own configs.
- Apps don't compete or overlap. Each has a distinct time shape, trigger, and audience.

## Data Flow

1. **Input** — a document (`.pdf` or `.docx`) is uploaded via the UI or pointed at by the CLI.
2. **Chunker** — parses the document into ordered `ContentBlock`s.
3. **Block consumers** (both run on the chunker's output):
   - `pd_reviewer` grades the blocks against a rubric → produces a review report.
   - `evidence` runs `extract → bind → appraise` over the blocks → produces `Claim` records.
4. **Output** — both consumers return their results to the caller. The Streamlit UI shows them and offers downloads; the CLI writes them to files.
5. **Deferred** — a persistent substrate (Delta on EDP) and a curation layer will land later. Future apps (`pd_watch`, `pd_gate_assembler`) consume that persistence.

Every transformation in the active path is stateless. The CLI / UI is the consumer of each run's output.

## Statelessness Today, Persistence Later

Both substrate pipelines are stateless:

- **chunker** — parse a document, return `ContentBlock`s. Regenerable from the source. Output ephemeral unless the caller writes it.
- **evidence** — parse → extract → bind → appraise. Returns `Claim`s. No store in the active path; the binder is the only LLM step.

Persistence (Delta tables in Unity Catalog on EDP, plus a separate curation layer for human annotations) is a **deferred consumer** of the pipelines. When it lands, it consumes pipeline output the same way the CLI/UI does today; the pipelines themselves don't change. `pd_watch` requires persistence to detect change, so it stays planned until then.

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

- **Biomedical knowledge graphs** (OpenTargets, MONDO, ClinicalTrials.gov, etc.): selectively ingested as claims with `source_type=knowledge_graph`.
- **WHO PPCs, TPPs, and peer-org product profiles** (FIND, CEPI, MMV, DNDi, etc.): downloaded into `documents`, chunked, then mined into `claims` with `source_type=product_profile`.
- **Causal / EHR-backed modeling** (PyWhy, OHDSI, partner platforms): model runs emit claims with `claim_type=modelled_impact` and `source_type=model_run`.

In each case, the substrate ingests **findings**, not engines or raw datasets. This keeps the substrate from collapsing into "the place where all data lives."

## Design Rules

These are load-bearing. Violations create overlap and force rewrites.

1. **PD-specific logic never enters the substrate.** Domain enters through injected configs.
2. **Substrate pipelines are stateless.** Same input → same output (modulo small LLM drift in the binder). No persistence in the active path. Persistence and curation are deferred consumers.
3. **One writer per asset (when persistence lands).** Substrate tables written only by substrate pipelines; app tables only by their owning app; annotations only by humans.
4. **Apps don't read each other's internals.** They consume published outputs.
5. **One claim = one assertion.** Atomicity is what makes downstream comparison and filtering real.
6. **Provenance is required.** No source, no claim.
7. **Labels, not gatekeeping.** Weak evidence is stored and labeled weak; consumers decide weight.
8. **Re-ingestion is a full rewrite per `source_id`.** Pipelines never edit existing claim rows; human curation lives in a separate, non-cascading table.

## Build Order

The system is built bottom-up. Each layer is shippable on its own; apps grow against an existing substrate.

Shipped:

1. **Chunker** (`.docx` and `.pdf` parsers, mapper, configs, CLI, Streamlit UI).
2. **pd_reviewer** (rubric grading on chunker output, CLI, Streamlit UI).
3. **Evidence pipeline** (Claim schema, `product_profile` extractor, binder, appraiser, stateless orchestrator, CLI, Streamlit UI). Imports chunker for parsing.

Next:

4. **Real `AttributeConfig` YAMLs** (vaccine first, then drug / diagnostic / device).
5. **Run the evidence pipeline against a real WHO PPC** end-to-end and validate the config.
6. **pd_reviewer grounding** — pd_reviewer optionally calls the evidence pipeline or reads its output to surface evidence behind each attribute.
7. **Additional evidence extractors** (paper, trial, knowledge_graph, model_run, …) — same pipeline shape, one new file per source type.

Deferred (require persistence): persistent substrate, curation layer, temporal operations, and the temporal/episodic apps. Shapes will be designed when scheduled.

## Repository Layout

```
pdis/
  llm_client.py          shared — LLM provider abstraction (Anthropic, OpenAI)
  chunker/             library — document parsing (.docx + .pdf) + mapping
  evidence/            library — stateless claim pipeline (extract → bind → appraise)
  pd_reviewer/         library — TPP rubric grading
  pd_watch/            library — temporal change detection (planned, needs persistence)
  pd_gate_assembler/   library — stage-gate decision packaging (planned)
  tools/               Streamlit UI suite over the libraries above
    app.py             entry point: `streamlit run tools/app.py`
    chunker_tool.py
    evidence_tool.py
    pd_reviewer_tool.py
    _widgets.py        shared sidebar widgets
```

Each library has its own README, requirements, and configs and is importable headlessly (no Streamlit dependency). The Streamlit layer lives in `tools/`. Libraries never import from `tools/`. `evidence` and `pd_reviewer` import from `chunker` for parsing; the reverse is not allowed.


## Where To Start

- New to the system → read this file, then `chunker/README.md`, then `evidence/README.md`.
- Adding a new TPP family → write an `AttributeConfig` YAML and a chunker `DocumentTypeConfig` YAML. No code changes in the substrate.
- Adding a new evidence source → add an `evidence/stages/extractor_<source_type>.py` that emits `Claim` records. No substrate changes.
- Adding a new app → create a sibling folder. Consume substrate via the documented contract. Do not modify substrate to fit the app.

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
