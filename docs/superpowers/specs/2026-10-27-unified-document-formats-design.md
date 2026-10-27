# One set of document formats for every tool

## Intent

Users hold their source material as Word, PowerPoint, Excel and PDF files, and every tool
judges documents. Accepting a format in one tool and refusing it in another made the tools
behave as if they read different kinds of evidence. Every tool and Ask now accepts the same
four formats, through one reader per format, so a passage has one shape and one stated
limitation wherever it is read.

## Decisions

- **The formats are DOCX, PPTX, XLSX and PDF, everywhere.** Inspector, Aligner, Screener,
  Scout, Chunker and Ask attachments accept exactly that set. There is no per-tool format
  list and no `accepted_suffixes` option: `services/chunker/formats.py` declares the set
  once, and the web's `document-formats.ts` mirrors it under its existing parity test.
- **One reader per format, shared by everyone.** A tool never reads a file itself. What a
  tool does with passages is its own; how a file becomes passages is Chunker's alone.
- **DOCX, PPTX and XLSX are the structured formats.** Their passages carry the structure the
  file declares, cite exactly, and trace to the passage.
- **PDF is the one less precise mode, and its limits are the same everywhere.** Unchanged
  from Screener's reader: one text passage and one page image per page, the
  `pdf_text_layout` warning on every passage, page-level traces, no inferred headings or
  table cells, no OCR, and whole-document refusal for encrypted, malformed, over-limit or
  textless input. Every tool already renders `DocumentExtractionNotice` from the passages, so
  the caveat is one sentence in one component. Weaker results where a tool leans on
  structure (Inspector's section mapping, Scout's table targets) are consequences of that one
  limit, not separate PDF paths.

## The Excel reader

Code keeps the layout faithfully; the tools' models interpret it, exactly as for a DOCX
table. The reader decides nothing semantic.

- **Values are what the file last calculated** (`data_only`), written the way Excel
  displays the kinds it can state exactly: integers without `.0`, percentages from a `%`
  number format, dates as ISO dates. A formula with no stored result is refused, with the
  instruction to open and save the file: reading it as empty would report a value as absent.
- **Regions.** A sheet's filled cells split into regions at fully blank rows. A region is
  layout, not a declared table, so it creates no Screener expansion group.
- **Rows.** A multi-column region follows the DOCX rule: its first row supplies the column
  headers, and each later row is one `table_row` passage serialized by the same
  `serialize_table_row` DOCX uses, with `table_cells`. A region's leading row holding a
  single filled cell is its title. A one-column region yields one paragraph per cell; a
  one-row region yields one paragraph joining its cells.
- **Context.** Every passage's `heading_stack` is the sheet name, then the region title when
  there is one, so a row is read with what it is about. Location is
  `structural_meta.sheet` and `cell_range` (`Targets!B4:F4`). Merged ranges repeat their
  value across the cells they cover, as a DOCX merged cell does.
- **Hidden sheets are read and marked** (`hidden_sheet: true`), never dropped silently.
- **Visuals.** Embedded raster images are image passages through the existing image-asset
  path; charts are recorded with the existing `unsupported_document_visual` warning.
- **Bounds.** Over 20 MB, or over the row bound, the whole workbook is refused with its
  reason, as an over-limit PDF is.
- **Legacy `.xls`** converts to XLSX through the LibreOffice already in the image, then reads
  as XLSX; its passages say `xls` as their source format.

## Non-goals

No OCR, no CSV, no model-written description of a sheet, no inferred header rows beyond the
DOCX rule, and no change to how any tool judges passages.

## Builder's discretion

Exact row bound, number rendering beyond the kinds above, trace-viewer grouping of sheets,
and test layout.
