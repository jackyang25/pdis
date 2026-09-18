# Document source fidelity and trace coherence

## Goal

Improve extraction completeness and make retained source material coherent across
Chunker, Inspector, Aligner, Scout, Screener, saved results, Assistant, and the
document trace. Preserve tool-specific assessment authority. Do not introduce
OCR, inferred chart boundaries, reconstructed PDF tables, or AI-written source text.

## Confirmed evidence

The supplied Screener export contains:

- PPTX: 592 blocks, 13 embedded-picture assets, no full-slide assets, and no
  extraction warnings. The trace cannot display slide renders absent from the file.
- PDF: 27 page-text blocks and 30 embedded-picture blocks, with the existing PDF
  limitation warning. Page 4's timeline uses vector drawing commands; extracted
  labels do not preserve bar/date relationships.
- A separate local rendering check succeeded for all 37 PPTX slides. This does
  not establish why the original run fell back; its runtime logs are unavailable.
- A synthetic DOCX reproduced omitted text-box and header text while ordinary
  body text survived. Existing extraction/mapping tests passed (31 tests).

Do not commit the user's documents or saved result as fixtures. Use synthetic
fixtures for checked-in tests and the supplied files for local acceptance checks.

## Architecture

Keep ContentBlock as the citable unit. A slide or page is a source location shared
by its blocks, not a replacement for every analysis unit within it. Extend the
existing location metadata and trace grouping instead of creating parallel source
collections. A document owns its retained sources once.

Use format-aware extraction behind the same public Chunker boundary:

- DOCX retains authored paragraph/table/image structure and document order. Add
  meaningful text-box content and referenced footnote/endnote content using
  explicit OOXML relationships. Headers/footers remain identified as such and
  are not repeated for imagined pages. Unsupported visual objects must produce
  an explicit limitation, not invented descriptions or silent completeness.
- PPTX retains text, table, and speaker-note blocks for section mapping and
  precise citations. Retain one rendered slide visual per slide and its existing
  slide identity. Individual picture extraction is a degraded fallback, not a
  second successful representation alongside the render.
- PDF retains page text plus one rendered page visual using the existing PDFium
  dependency. Replace the embedded-raster-only visual path rather than keeping
  both. Do not infer semantic elements or text reading order from coordinates.
  PDF remains opt-in for Screener only.

PDF page rendering deliberately supersedes the current no-page-rendering policy;
update the relevant repository invariant, capability documentation, and tests in
the implementation. Preserve the current refusal of encrypted, malformed,
over-limit and textless PDFs; scan/OCR support is a separate capability.

## Extraction outcomes

Use a shared machine-readable extraction-warning vocabulary and shared notice
presentation. Retain warnings in portable blocks/results and include their meaning
in model context. Presentation derives document-level notices from retained data.

Distinguish missing renderer, failed rendering, unsupported source content, and
limited PDF text structure. Never infer a historical warning from missing data in
an old artifact. A historical file can lack coverage information without claiming
that a failure was observed.

Rendering is bounded by explicit page/pixel/output limits and conversion timeouts.
Avoid silently dropping pages to fit limits. PDF rendering failure refuses the new
visual-preserving parse; PPTX's existing picture fallback remains available only
with an explicit degraded-coverage notice. Do not claim rendered output is always
pixel-identical to Microsoft Office or guarantees successful AI interpretation.

## Provenance and validation

Share source membership and line-span resolution, not tool verdict rules.

- A text quotation is copied/resolved from retained canonical text. Keep existing
  normalization semantics; do not substitute OCR or model transcription.
- A visual reference names a retained visual block. It does not masquerade as a
  quotation of the image's labels or use `[image]` as supporting quoted prose.
- Tool-specific schemas must explicitly allow visual references where their
  assessments accept visual evidence. Keep necessary text requirements for
  Scout's numeric targets; a visual cannot bypass exact target-text validation.
- A page image does not validate extracted reading order. A found PDF quote only
  establishes correspondence with retained text, not correct table interpretation.
- Do not fabricate image coordinates. Without proven text-to-image coordinates,
  a text citation reveals its text block within its slide/page group.

Keep Inspector's section selection and whole-document scope distinct. One section
label per smaller content block remains intact. A slide visual must not implicitly
route every topic on that slide through one arbitrary section. Visual context
sharing must use explicit same-slide identity, with the supplied source IDs retained
and checked, rather than guessed semantic linkage.

## Trace and source panels

DOCX stays a flowing document; PPTX and PDF use declared slide/page groups.
Identify the retained overview as `Slide visual` or `Page visual`, not a generic
`[image]` caption. Make extracted text accessible within the same group and open
the relevant text when following a quote. Preserve direct block links, source-list
navigation, keyboard access, and retained citations even when content is collapsed.
Do not treat the image and its extracted text as independent corroboration.

Use the shared viewer/source-panel components. No per-tool document viewers and
no browser parsing or guessed missing assets. Dense visuals need an accessible
larger-view affordance; fitting a page thumbnail is not enough to inspect labels.

## Portability and compatibility

Retain original stable source IDs within each saved run. New parsing can produce
different IDs; never remap an old finding onto newly parsed blocks by position.
Do not rewrite previous exports or generate missing visuals during import.
Any changed citation schema requires explicit analysis-version handling for each
affected tool. Accept old artifacts only when their original guarantees can be
preserved without fabricated provenance; otherwise refuse with a clear message.
The original binary documents remain outside the portable result.

## Alternatives rejected

1. Image-only slide/page blocks: loses line-based quoting and mixed-topic routing.
2. Automatic chart/figure segmentation: adds inferred boundaries and unreliable
   grouping of PDF drawing operations.
3. Independent new page-source store beside current blocks: duplicates ownership
   and creates another lineage path to maintain.

## Acceptance checks

- Synthetic DOCX body, table, text-box, reference-note, header/footer and unsupported
  visual cases verify content retention, locations and explicit limitations.
- PPTX mixed-topic slide, grouped content, chart, table, notes, full rendering and
  forced fallback cases verify correct mapping inputs and coverage reporting.
- PDF vector timeline, multi-column text, embedded picture and existing refusal
  cases verify one page visual, retained text, locations and bounded processing.
- Inspector, Aligner, Scout and Screener tests verify unchanged assessment scope,
  source membership, valid text ranges, visual references, and rejected fake quotes.
- Export/import and Assistant tests preserve assets, warnings and source identity.
- Browser tests cover citation navigation, automatic revelation of cited text,
  image enlargement, keyboard controls, and narrow layouts without duplicate paths.
- Repeat real-file parsing locally; inspect assets and trace groups, not just asset
  counts. No paid AI runs without explicit authorization. Offline tests cannot prove
  improved semantic accuracy; report that remaining limitation in the handoff.

## Delivery boundaries

Implement source outcomes/extraction first, provenance consumers second, and shared
trace presentation third, each with failing regressions before changes. Remove
superseded paths as replacements pass. Preserve unrelated staged Scout changes.
Do not push, deploy, or regenerate user results as part of this cleanup.
