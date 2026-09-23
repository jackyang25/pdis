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

DOCX also retains text boxes, referenced footnotes/endnotes, and headers/footers,
including their supported tables and images. Images resolve against the part that
owns them; repeated note references do not duplicate the note. Supplementary parts
carry their explicit document-part identity, not guessed page numbers, and
headers/footers do not inherit body heading context. Unsupported native drawings,
charts, SmartArt and embedded objects carry a limitation warning rather than invented
text. This is structured extraction, not a pixel-identical Word rendering.
Unsupported-visual warnings retain the detected object kind and source-part
location. These describe structure, not importance: even a header drawing remains
flagged, and consumers do not guess whether it is decoration. Older saved blocks
without object details keep a general warning.

Input capabilities live in `formats.py`. `DOCUMENT_SUFFIXES` is the default:
DOCX/PPTX declare tables, rows, headings and order. A caller may explicitly pass
`accepted_suffixes=TEXT_EXTRACTION_SUFFIXES` to `run_pipeline` to also accept
text-based PDF. Only Screener enables that capability; standalone Chunker,
Inspector, Aligner, Scout, Archivist builds and Ask attachments keep the default.

PDF uses pypdf for one text block per page and PDFium for one full-page image,
with stable IDs, a one-based `structural_meta.page`, and
`extraction_warnings: ["pdf_text_layout"]`. Text IDs remain unchanged. The page
visual retains visible drawings and grouped images without publishing fragmented
pictures separately. No OCR, inferred headings, reconstructed table cells, or
guessed figure boundaries are used. Columns may be misordered in extracted text;
a quote match does not verify table interpretation. The viewer shows the page
visual first and keeps cited text reachable in an expandable section.

PPTX uses the same image-asset contract for one rendered overview per slide,
alongside native text, tables, and notes. If rendering is unavailable or fails,
embedded pictures remain and all retained blocks carry the corresponding warning.
Rendering is bounded to 200 pages, 20 million pixels per page and 100 MiB of PNG
bytes per document, with a 120-second LibreOffice conversion timeout. PDFium calls
are serialized within each process; incomplete rendered coverage is refused.
These are resource guards, not a hard memory sandbox.

Saved results preserve the extraction they actually received. Historical
`pdf_limited_structure` warnings remain readable; imports do not invent full-page
or full-slide assets. Rerun the original document for improved coverage.

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

DOCX table blocks also carry `structural_meta.table_group`, derived from the owning
XML part and table path. It distinguishes supplementary tables whose numeric
`table_index` can coincide. Native nested tables retain the outer table's group
for context; independently anchored supplementary tables keep their own identity.
This adds structural metadata without changing source text or citation IDs.

Section mapping uses a schema-bound closed taxonomy. Every parsed block must be
labeled exactly once; unknown, duplicate, or omitted block IDs fail the mapping
boundary rather than entering downstream tools as partial document context.
Mapping stays in one request when its strict schema fits. If the block-ID enum
exceeds the provider's count or string-size limits, only the requested output IDs
are partitioned; every request retains the complete document text and visuals.
Bounded parallel requests validate their own IDs, and all labels are validated
together before being applied. No blocks are dropped and strict output is not
disabled. This bounds schema size, not document context or model output tokens.

## Development

Configs use `{org}_{source_type}_{intervention}.yaml`. Pillow normalizes raster
formats. LibreOffice is an optional boundary for vector conversion and full-slide
rendering. Chunker imports no other service.
