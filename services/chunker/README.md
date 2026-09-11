# Chunker

Convert supported documents into ordered, citable content blocks.

## Background

Chunker is the shared document boundary. It preserves source order, stable block
IDs, provenance, tables, and visuals without replacing images with generated
descriptions.

## Usage

Import pipeline entry points, config lookup, `ContentBlock`, `ImageAsset`, and
serializers from `services.chunker`.

## Contract

| Direction | Value |
|---|---|
| Input | A document, stable `doc_id`, optional `DocumentTypeConfig`, and provenance |
| Output | Ordered `ContentBlock` records with stable IDs and retained visuals |

The API supplies the original filename stem as `doc_id`; temporary upload names
never enter citations. DOCX preserves body order and embedded images; PPTX
retains slide text, tables, notes, positions, and rendered slide images when
available.

Input capabilities live in `formats.py`. `DOCUMENT_SUFFIXES` is the default:
DOCX/PPTX declare tables, rows, headings and order. A caller may explicitly pass
`accepted_suffixes=TEXT_EXTRACTION_SUFFIXES` to `run_pipeline` to also accept
text-based PDF. Only Screener enables that capability; standalone Chunker,
Inspector, Aligner, Scout, Archivist builds and Ask attachments keep the default.

PDF uses pypdf to produce one text block per page, with stable IDs, a one-based
`structural_meta.page`, and `extraction_warnings: ["pdf_limited_structure"]`.
Directly placed embedded rasters (including inline images) use pypdf's image decoding and the
existing canonical image asset path. Each page's text is followed by its images
in resource order, not inferred reading order. Text IDs remain unchanged; image
IDs append `-image-0001`, etc. to the page's text ID. Reused resources are retained
per page, not per placement. Unused resources are excluded. Nested Form images
are skipped: pypdf's display flag is page-local, so including them could cite
unused resources. This limitation is disclosed, not reconstructed with custom
PDF traversal. Images may be fragments of a larger figure.
No headings, table cells, vector drawings, OCR, or page rendering are inferred.
Columns may be misordered; a citation is not a verified page reconstruction.

PDF parsing refuses encrypted files (including empty-password encryption), strict
parse failures, image decoding failures, logged pypdf extraction warnings, zero-page files, files over
20 MiB or 200 pages, and direct content streams over 5 MiB decoded. This cap does
not include nested Form XObject streams. Any page with no non-whitespace text fails the whole
document, including blank pages: it cannot reliably distinguish an intentional
blank from an unreadable scan. These are input/extraction guards, not an accuracy
certificate or a hard memory sandbox; stream decompression occurs before the
decoded-size check. No partial document is returned on failure.
The API's logging composition keeps pypdf warnings enabled even at quieter
`LOG_LEVEL` settings because some library errors are only logged. Other hosts
using the PDF capability must also leave pypdf warning diagnostics enabled;
Chunker observes each parsing thread separately and removes its handler on exit.

Multi-column table rows retain both their canonical searchable `content` and
ordered `table_cells` with exact content offsets. Consumers render columns from
those cells and fall back to canonical text when structured cells are not
available; they never reconstruct cells by splitting prose.

Section mapping uses a schema-bound closed taxonomy. Every parsed block must be
labeled exactly once; unknown, duplicate, or omitted block IDs fail the mapping
boundary rather than entering downstream tools as partial document context.

## Development

Configs use `{org}_{source_type}_{intervention}.yaml`. Pillow normalizes raster
formats. LibreOffice is an optional boundary for vector conversion and full-slide
rendering. Chunker imports no other service.
