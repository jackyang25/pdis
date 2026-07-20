# Chunker

Parses documents (`.docx`, `.pdf`, `.pptx`) into ordered, citable
`ContentBlock`s. Embedded DOCX visuals and rendered PPTX slides become portable
image assets; an optional LLM mapper labels sections without replacing visuals
with generated text.

## Inputs and outputs

| | |
|---|---|
| Input | One document (`.docx`, `.pdf`, or `.pptx`) + header `(org, source_type, intervention_class, indication)` |
| Output | `list[ContentBlock]` — each block stamped with the header |

The caller must pass the original filename stem as `doc_id` when parsing a
temporary upload. Stable IDs are derived from this value, so temporary names
must never reach downstream citations. The header is stamped on every block so
downstream tools can route by provenance.
Image blocks carry a typed image payload (`media_type`, base64 bytes, hash, and
source media type). The mapper, Reviewer, Scout's document-reasoning stages, and
Ask receive those visuals as block-labeled multimodal inputs.

## Files

| File | Purpose |
|---|---|
| `models.py` | `ContentBlock` and `DocumentTypeConfig` dataclasses; YAML loader. |
| `pipeline.py` | `run_pipeline(file, doc_id, ...)` — parse → optional label. |
| `stages/parser.py` | Format dispatcher for DOCX, PDF, and PPTX. |
| `stages/parser_docx.py` | Walks Word XML in body order; populates `heading_stack` from heading styles. |
| `stages/parser_pdf.py` | `pdfplumber`-based; populates `structural_meta.page`. |
| `stages/parser_pptx.py` | Extracts slide titles, text, tables, notes, positions, and portable visuals. |
| `stages/image_assets.py` | Resolves DOCX image relationships and attaches portable raster assets. |
| `stages/rasterizer.py` | Optional LibreOffice boundary for vectors and PPTX slide rendering. |
| `stages/mapper.py` | LLM section-labeler; constrained to the config's `section_taxonomy`. |
| `cli.py` | Headless batch export to CSV/JSONL. |
| `configs/` | One YAML per `(org, source_type, intervention)` combination. |

## Configs

Filename: `{org}_{source_type}_{intervention}.yaml`. Each file declares the
section taxonomy the mapper labels against. Bundled BMGF configs cover `itpp`
and `ctpp` for vaccine, drug, diagnostic, and device, plus `ipdp` for vaccine,
drug, and diagnostic. `CONFIG_TEMPLATE.yaml` documents the extension shape.

## Public contract

From `__init__.py`:

- `run_pipeline`, `run_pipeline_batch`, `map_blocks_batch`
- `ContentBlock`, `DocumentTypeConfig`, `PipelineResult`
- `find_config`, `blocks_to_dicts`
- `DEFAULT_MAX_OUTPUT_TOKENS`

External callers (`api/routes/chunker.py`, `reviewer`, `scout`) import only from this surface.

## Dependencies

Chunker is the root of the service graph and imports from no service. Standard
raster images need no system dependency. LibreOffice Draw converts unsupported
vector formats; LibreOffice Impress plus PDFium renders complete PPTX slides.
When rendering is unavailable, PPTX text/tables still parse and embedded
pictures are retained as the visual fallback.
