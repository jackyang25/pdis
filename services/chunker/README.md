# Chunker

Parses documents (`.docx`, `.pdf`) into ordered, citable `ContentBlock`s. Optionally labels each block with a section name using an LLM mapper.

## Inputs and outputs

| | |
|---|---|
| Input | One document (`.docx` or `.pdf`) + header `(org, source_type, intervention_class, indication)` |
| Output | `list[ContentBlock]` — each block stamped with the header |

The header is stamped on every block so downstream tools can route by provenance.

## Files

| File | Purpose |
|---|---|
| `models.py` | `ContentBlock` and `DocumentTypeConfig` dataclasses; YAML loader. |
| `pipeline.py` | `run_pipeline(file, doc_id, ...)` — parse → optional label. |
| `stages/parser.py` | Dispatcher: `.docx` → `parser_docx`, `.pdf` → `parser_pdf`. |
| `stages/parser_docx.py` | Walks Word XML in body order; populates `heading_stack` from heading styles. |
| `stages/parser_pdf.py` | `pdfplumber`-based; populates `structural_meta.page`. |
| `stages/mapper.py` | LLM section-labeler; constrained to the config's `section_taxonomy`. |
| `cli.py` | Headless batch export to CSV/JSONL. |
| `configs/` | One YAML per `(org, source_type, intervention)` combination. |

## Configs

Filename: `{org}_{source_type}_{intervention}.yaml`. Each file declares the section taxonomy the mapper labels against. Bundled:

- `bmgf_tpp_vaccine.yaml`
- `bmgf_tpp_drug.yaml`
- `bmgf_tpp_diagnostic.yaml`
- `bmgf_tpp_device.yaml`

## Public contract

From `__init__.py`:

- `run_pipeline`, `run_pipeline_batch`, `map_blocks_batch`
- `ContentBlock`, `DocumentTypeConfig`, `PipelineResult`
- `find_config`, `blocks_to_dicts`
- `DEFAULT_MAX_OUTPUT_TOKENS`

External callers (`api/routes/chunker.py`, `reviewer`, `monitor`) import only from this surface.

## Dependencies

None — chunker is the root of the service graph. Other services import from chunker; chunker imports from no service.
