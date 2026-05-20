# Benchmarker

Turns a source document into a flat list of source-backed `Claim`s bound to an attribute namespace. The output is the peer corpus that Reviewer benchmarks new drafts against.

> Folder: `services/benchmarker/` · User-facing name: **Benchmarker** · Data unit: `Claim`

## Inputs and outputs

| | |
|---|---|
| Input | One document + header `(org, source_type, intervention_class, indication)` |
| Output | `list[Claim]` — each claim stamped with the header and bound to an attribute in the rubric's namespace |

Pipeline: parse (chunker) → extract → bind → output.

## Files

| File | Purpose |
|---|---|
| `models.py` | `Claim`, `AttributeConfig`, `AttributeDef`; YAML loader; `validate_claim`. |
| `pipeline.py` | `run_pipeline(file_path, ...)` — orchestrates parse → extract → bind. |
| `stages/extractor_product_profile.py` | LLM extractor for `source_kind=product_profile`. Requires every claim to cite a real `block_id` and a verbatim `quote`. |
| `stages/binder.py` | LLM binder; assigns `attribute_ref` from the config's vocabulary. |
| `store.py` | `ClaimsStore` Protocol + `FileClaimsStore` (folder of JSONL → in-memory list). |
| `cli.py` | Headless batch export to JSONL/CSV. |
| `configs/` | One YAML per intervention class. |

## Configs

Filename: `{intervention}.yaml` — keyed by intervention only because the attribute namespace describes the product class, not the document format. Bundled: `vaccine.yaml`. Each file declares:

- `attributes` — the constrained vocabulary the binder picks from
- `claim_types` — allowed claim_type values
- `indications` — allowed indication values (drives the UI picker)
- `preamble` — domain context injected into the binder prompt

## Public contract

From `__init__.py`:

- `run_pipeline`, `run_pipeline_batch`, `default_source_id_from_path`
- `Claim`, `AttributeConfig`, `BatchResult`
- `ClaimsStore`, `FileClaimsStore`
- `find_config`, `claims_to_dicts`
- `EXTRACTORS`, `DEFAULT_MAX_OUTPUT_TOKENS`

## Storage

Today the store is a folder of JSONL files at `data/claims/`. Tomorrow it becomes a Delta table; the `ClaimsStore` Protocol stays the same.

## Dependencies

Imports from `chunker` (parser). Never imports from `reviewer`.
