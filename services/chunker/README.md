# Chunker

Parses documents (`.docx`, `.pdf`) into ordered, citable `ContentBlock`s. Embedded DOCX visuals become portable image assets; an optional LLM mapper labels sections without replacing visuals with generated text.

## Inputs and outputs

| | |
|---|---|
| Input | One document (`.docx` or `.pdf`) + header `(org, source_type, intervention_class, indication)` |
| Output | `list[ContentBlock]` — each block stamped with the header |

The header is stamped on every block so downstream tools can route by provenance.
Image blocks carry a typed image payload (`media_type`, base64 bytes, hash, and
source media type). The mapper, Reviewer, Scout's document-reasoning stages, and
Ask receive those visuals as block-labeled multimodal inputs.

## Files

| File | Purpose |
|---|---|
| `models.py` | `ContentBlock` and `DocumentTypeConfig` dataclasses; YAML loader. |
| `pipeline.py` | `run_pipeline(file, doc_id, ...)` — parse → optional label. |
| `stages/parser.py` | Dispatcher: `.docx` → `parser_docx`, `.pdf` → `parser_pdf`. |
| `stages/parser_docx.py` | Walks Word XML in body order; populates `heading_stack` from heading styles. |
| `stages/parser_pdf.py` | `pdfplumber`-based; populates `structural_meta.page`. |
| `stages/image_assets.py` | Resolves DOCX image relationships and attaches portable raster assets. |
| `stages/rasterizer.py` | Optional LibreOffice boundary for EMF/WMF/SVG → PNG. |
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

External callers (`api/routes/chunker.py`, `reviewer`, `scout`) import only from this surface.

## Dependencies

Chunker is the root of the service graph and imports from no service. Standard
raster images need no system dependency. LibreOffice is an optional runtime
dependency used only to convert unsupported vector formats to PNG.
