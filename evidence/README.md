# Evidence

Evidence turns a source document (a WHO PPC, a TPP, a paper) into a flat list of source-backed `Claim` records bound to an `AttributeConfig`. The pipeline is **stateless**: document in, claims out. The caller (Streamlit UI or CLI) decides what to do with the output — display, download, or hand off to the next consumer.

It uses the chunker as a library for parsing, then runs four pipeline stages over the parsed blocks: extract → bind → appraise → output.

## Files

| File | Purpose |
|---|---|
| `models.py` | Shared dataclasses: `Claim`, `AttributeDef`, `AttributeConfig`; YAML config loader; canonical enums for `claim_type`, `source_type`, `polarity`, `evidence_strength`, etc.; `validate_claim`. |
| `stages/extractor_product_profile.py` | Deterministic extractor for `source_kind=product_profile` (WHO PPCs, TPPs, peer-org equivalents). Reads chunker `table_row` blocks and emits draft claims per Minimum/Preferred cell. One file per source type — mirrors chunker's `parser_docx.py` / `parser_pdf.py` pattern. |
| `stages/binder.py` | LLM-driven attribute binding. Picks `attribute_ref` for each claim from the `AttributeConfig`'s constrained vocabulary. Mirrors `chunker/mapper.py`. |
| `stages/appraiser.py` | Heuristic reliability labeling. Sets `evidence_strength` from `source_type` defaults and `recency_tier` from claim dates. |
| `pipeline.py` | Stateless orchestrator: `run_pipeline(file_path, ...) → (blocks, claims)`. Wires parse → extract → bind → appraise. |
| `cli.py` | Headless CLI: takes a folder of source documents + a config, writes `claims.jsonl`, `claims.csv`, and `summary.csv`. |
| `configs/` | `AttributeConfig` YAML files (one per product class). `CONFIG_TEMPLATE.yaml` is the starter. |
| `requirements.txt` | Library runtime dependencies (no Streamlit). |

The Streamlit UI for this library lives in `tools/evidence_tool.py`.
LLM provider abstraction is shared at the repo root: `llm_client.py`.

Evidence imports chunker APIs for parsing:

- `chunker.stages.parser.parse_document` (called from `evidence.pipeline.run_pipeline`)
- `chunker.models.ContentBlock`

Evidence does **not** import the chunker mapper. The binder uses `heading_stack` and block content directly; section labels from the mapper are not part of evidence's pipeline.

## Setup

From the repository root:

```bash
source .venv/bin/activate
python -m pip install -r chunker/requirements.txt
python -m pip install -r evidence/requirements.txt
```

Set an API key in the environment or enter it in the Streamlit sidebar:

```bash
export ANTHROPIC_API_KEY="your-key"
# or
export OPENAI_API_KEY="your-key"
```

## Run

Use the unified root app:

```bash
streamlit run tools/app.py
```

Or evidence directly:

```bash
streamlit run tools/evidence_tool.py
```

The Streamlit UI flow:

1. Sidebar — pick the document **header** (`org · source_type · intervention`) and optional `therapeutic_area` at the top of the app. Pick **Evidence** as the tool.
2. Upload a `.docx` or `.pdf`.
3. Click **Run Pipeline**. The pipeline parses, extracts, binds, and appraises.
4. Inspect the resulting claims; download as JSONL or CSV.

For batch / scripted runs, use the CLI (header flags identify the document type):

```bash
python -m evidence.cli \
  documents/ \
  out/ \
  --org gates \
  --source-type tpp \
  --intervention vaccine \
  --therapeutic-area malaria \
  --provider anthropic \
  --max-workers 4
```

Outputs `out/claims.jsonl`, `out/claims.csv`, `out/summary.csv`. Every claim is stamped with the full header (org, source_type, intervention_class, therapeutic_area).

## AttributeConfig

Evidence configs are keyed by **intervention only** — the attribute namespace describes a product class (vaccine, drug, diagnostic, device), not a document format. Claims from a Gates TPP vaccine document and a WHO PPC vaccine document bind to the same `vaccine.*` namespace. Source provenance (`org`, `source_type`) is preserved on each claim via the header.

```text
configs/CONFIG_TEMPLATE.yaml      # copy and customize for new product classes
configs/vaccine.yaml              # shipped
configs/drug.yaml                 # planned
configs/diagnostic.yaml           # planned
configs/device.yaml               # planned
```

The config defines:

- `type_key`: stable identifier (matches filename stem, e.g., `vaccine`).
- `display_name`: UI label.
- `intervention_class`: the product class this config is for. Must match the filename stem.
- `attributes`: list of `{name, description, parent?, expected_claim_types?}`. Each is a valid `attribute_ref` for binding.
- `claim_types`: allowed `claim_type` values for this config.
- `therapeutic_areas`: allowed `therapeutic_area` values.
- `preamble`: domain context injected into the binder prompt.
- `disambiguation`: free-text rules for ambiguous binding.

Adding a new product class = adding `<intervention>.yaml`. No code changes.

## How The Pipeline Works

Five stages, each owning one slice of the `Claim`:

| # | Stage | Transformation |
|---|---|---|
| 1 | `chunker.parse_document` | Document → `list[ContentBlock]` |
| 2 | `stages/extractor_<source_type>.extract_<source_type>` | `list[ContentBlock]` → draft `list[Claim]` (`attribute_ref=None`, strength/recency `None`) |
| 3 | `binder.bind_claims` | draft `list[Claim]` → bound `list[Claim]` (LLM fills `attribute_ref` + `binding_confidence`) |
| 4 | `appraiser.appraise_claims` | bound `list[Claim]` → finalized `list[Claim]` (heuristic `evidence_strength` + `recency_tier`) |
| 5 | `pipeline.run_pipeline` | assigns `id` / `ordinal`, returns `list[Claim]` to the caller |

| Stage | Owns | Config? | LLM? |
|---|---|---|---|
| Extractor | `statement`, `source_id`, `source_type`, `source_locator`, `claim_type`, `polarity`, `intervention_class`, `therapeutic_area`, `extracted_at` | no | no (deterministic for product_profile; future paper extractor will use LLM) |
| Binder | `attribute_ref`, `binding_confidence` | yes — `AttributeConfig` | yes |
| Appraiser | `evidence_strength`, `recency_tier` | no | no (heuristic) |
| Pipeline | `id`, `ordinal`, `version`, `review_status` | no | no |

Only the binder consumes the config. Only the binder uses an LLM. Everything else is deterministic.

## Claim Schema

A claim is one source-backed, atomic, decision-relevant assertion.

| Field | Type | Set by | Notes |
|---|---|---|---|
| `id` | string | pipeline | `{source_id}/c-{ordinal:04d}` |
| `ordinal` | int | pipeline | position in extraction order |
| `statement` | string | extractor | one normalized assertion |
| `claim_type` | string | extractor | `performance`, `feasibility`, `user_need`, `workflow`, `access`, `market`, `regulatory`, `modelled_impact`, `expert_judgment` |
| `polarity` | string | extractor | `supports`, `challenges`, `neutral` |
| `source_id` | string | caller | stable identifier for the source document |
| `source_type` | string | extractor | `paper`, `trial`, `regulatory_doc`, `product_profile`, `knowledge_graph`, `real_world_data`, `model_run`, `market_report`, `interview`, `expert_note` |
| `intervention_class` | string | extractor | type of intervention (vaccine, drug_oral, diagnostic_assay, …) |
| `therapeutic_area` | string or null | extractor | disease / use case (malaria, hiv, …); null for cross-area claims |
| `source_locator` | dict | extractor | verbatim anchor + retrievable locator (quote, page, block_id, doi, url, …) |
| `extracted_at` | ISO date | extractor | when the claim entered the substrate |
| `valid_as_of` | ISO date or null | extractor | for time-bound claims |
| `attribute_ref` | string or null | binder | matches one `name` from `AttributeConfig.attributes` |
| `binding_confidence` | string or null | binder | `high`, `medium`, `low` |
| `evidence_strength` | string or null | appraiser | `strong`, `moderate`, `weak`, `anecdotal` |
| `recency_tier` | string or null | appraiser | `current`, `aging`, `stale` |
| `review_status` | string | pipeline | `unverified` by default |
| `version` | int | pipeline | defaults to 1; reserved for future revision flow |
| `superseded_by` | string or null | pipeline | reserved for future revision flow |
| `notes` | string or null | extractor | optional |

### `source_locator` anchor requirements

The anchor is what makes a claim auditable. Required shape depends on `source_type`:

| Source type | Required anchor |
|---|---|
| paper, regulatory_doc, market_report, product_profile, interview | verbatim `quote` |
| trial | `nct_id` + structured field path |
| real_world_data | `dataset_id` + SQL filter / cohort definition |
| model_run | `run_id` + `model_version` + output reference |
| knowledge_graph | `kg_name` + `kg_version` + node/edge IDs |
| expert_note | attributed verbatim `quote` + date + context |

Every locator also carries a retrievable pointer (`url`, `doi`, or `path`).

## What Counts As Evidence

A claim must satisfy three properties. `validate_claim` enforces them.

1. **Source-backed** — traceable via `source_id` and a non-empty `source_locator`.
2. **Atomic** — one assertion per claim. Paragraphs defeat downstream filtering and comparison.
3. **Decision-relevant** — could support, challenge, or revise a TPP attribute, threshold, or scope choice.

Expert opinion counts when attributed and labeled honestly (`source_kind=expert_note`, low `evidence_strength`). Unsourced inherited assumptions do not.

## Evidence Sources (per `source_type`)

The same pipeline shape handles many source types; only the extractor varies.

| `source_type` | Examples | Today |
|---|---|---|
| `product_profile` | WHO PPCs, WHO TPPs, FIND / CEPI / MMV / DNDi / IAVI / Unitaid product profiles, internal historical TPPs | shipped |
| `paper` | Peer-reviewed papers, preprints, systematic reviews | planned extractor |
| `trial` | ClinicalTrials.gov, WHO ICTRP, EU CTR | planned extractor |
| `regulatory_doc` | FDA labels, EMA EPARs, WHO PQ dossiers, pathway guidance | planned extractor |
| `knowledge_graph` | OpenTargets, MONDO, HPO, DrugBank, ChEMBL, DisGeNET | planned extractor |
| `real_world_data` | OHDSI/OMOP EHRs, claims databases, registries | planned extractor |
| `model_run` | Causal / counterfactual modeling on EHR cohorts | planned extractor |
| `market_report` | CHAI, WHO GPRM, IQVIA, procurement records | planned extractor |
| `interview` | Structured interviews, focus groups, workflow studies | planned extractor |
| `expert_note` | Attributed advisory-panel statements, SAGE recommendations | planned extractor |

Each new source type = one new file `stages/extractor_<source_type>.py` (e.g., `extractor_paper.py`, `extractor_trial.py`). Same `Claim` shape downstream; binder/appraiser/pipeline don't change.

## Scoping: Intervention and Therapeutic Area

`attribute_ref` says *what the claim is about* (e.g., `vaccine.performance.efficacy_clinical_disease`). Two orthogonal fields say *what the claim applies to*:

- **`intervention_class`** — type of intervention (`vaccine`, `drug_oral`, `drug_lai`, `mab`, `diagnostic_assay`, `device`, …).
- **`therapeutic_area`** — disease / use case (`malaria`, `hiv`, `tb`, …).

Both are controlled vocabularies inside the `AttributeConfig`. Both are optional filters on retrieval (future). Cross-cutting claims (regulatory pathway facts) can have `therapeutic_area=None`.

Keeping these orthogonal to `attribute_ref` keeps the config small and lets the same vaccine config serve WHO PPCs *and* Gates TPPs *and* peer-org profiles, regardless of publisher or disease.

## Design Rules

Load-bearing. Violations either leak domain into the substrate or break determinism.

1. **No TPP-specific fields.** Domain enters through the injected `AttributeConfig`.
2. **One claim = one assertion.** Atomic by enforcement (`validate_claim`).
3. **Provenance is required.** Every claim must have a non-empty `source_locator`.
4. **Labels, not gatekeeping.** Weak evidence is stored and labeled weak.
5. **Pipeline is stateless.** Document in, claims out. Same input → same output (modulo small LLM drift in the binder). No persistence in the active path.
6. **One config consumer.** Only the binder reads the `AttributeConfig`'s attribute list; extractor / appraiser / pipeline do not.
7. **One-way dependency.** Evidence imports chunker. Chunker does not import evidence.
8. **Verifiability is the user's job; substrate makes it possible.** Every claim is auditable by a human in under 30 seconds via its verbatim anchor + locator.

## Status

Shipped:

- `Claim` and `AttributeConfig` dataclasses + validators.
- `product_profile` extractor (deterministic, table-driven).
- `stages/binder.py` (LLM-driven, constrained to config).
- `stages/appraiser.py` (heuristic).
- `pipeline.py` stateless orchestrator.
- `cli.py` headless CLI.
- `tools/evidence_tool.py` Streamlit UI (parse → extract → bind → appraise → display + download).
- `llm_client.py` shared provider-neutral adapter.

Deferred until needed: persistent claim store, curation layer, additional extractors, and temporal operations. Each is additive to the current pipeline; specifics will be designed when the work is scheduled.

The MVP target is to run the pipeline against one real document (the WHO Malaria Vaccines PPC) against a real `vaccine.yaml` config and validate the output is useful.
