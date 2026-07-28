# Chunker

Convert DOCX, PDF, and PPTX files into ordered, citable content blocks.

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
never enter citations. DOCX preserves body order and embedded images, PDF
preserves page metadata, and PPTX retains slide text, tables, notes, positions,
and rendered slide images when available.

Section mapping uses a schema-bound closed taxonomy. Every parsed block must be
labeled exactly once; unknown, duplicate, or omitted block IDs fail the mapping
boundary rather than entering downstream tools as partial document context.

## Development

Configs use `{org}_{source_type}_{intervention}.yaml`. Pillow normalizes raster
formats. LibreOffice is an optional boundary for vector conversion and full-slide
rendering. Chunker imports no other service.
