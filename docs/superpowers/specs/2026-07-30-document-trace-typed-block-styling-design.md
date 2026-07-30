# Document trace typed-block styling

## Goal

Make reconstructed document traces easier to scan using structure already
carried by canonical `ContentBlock`s, without inferring layout or changing any
analysis data.

## Scope

- Give `table_row` blocks a compact row surface so they read as structured
  records rather than indented paragraphs.
- Use a valid numeric `structural_meta.heading_level` to vary the visual weight
  and spacing of `heading` blocks. Fall back to the existing heading treatment
  when the level is absent.
- Preserve block order, text, images, highlights, block IDs, annotations, and
  all trace interactions exactly as stored.

## Boundaries

- Do not parse flattened table-row prose into cells or columns.
- Do not use `section_label` as presentation structure.
- Do not infer styling from arbitrary prose, parser coordinates, or the
  document's source format.
- Do not change Chunker, API schemas, result envelopes, or analysis services.
- Keep the renderer shared by every document trace consumer.

## Verification

- Add focused renderer coverage for heading levels, missing heading metadata,
  table rows, and ordinary paragraphs.
- Run the document-trace tests, web typecheck, production build, and
  `git diff --check`.
