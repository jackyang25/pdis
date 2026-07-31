# Document Trace View Design

## Purpose

Add a document-centered trace view that reconstructs the uploaded document from
its retained `ContentBlock`s and shows which existing Scout results were derived
from each cited passage. The view improves auditability without creating new
analysis, changing canonical results, or exposing chunk boundaries as visual
document structure.

## Scope

The first release provides:

- one shared, read-only document trace viewer;
- one Scout adapter that projects existing Scout lineage into annotations;
- continuous document-style rendering of retained text, tables, and images;
- exact-span highlighting when an existing result carries an exact quote;
- a restrained block marker when provenance identifies a block but no exact
  span;
- an inspector panel for the selected annotation; and
- filtering by the existing Scout result layer.

Inspector and Aligner can use the same viewer through separate future adapters.
They are not implemented in this release. The shared contract must not contain
Scout-specific fields.

## Non-goals

- Reproducing the original DOCX or PPTX layout pixel-for-pixel.
- Creating new claims, summaries, labels, relationships, or provenance.
- Recalculating imported final results.
- Adding an API endpoint, result-envelope field, database, or server session.
- Replacing the Evidence map. The map explains result-to-result relationships;
  this view explains result-to-document lineage.

## Architecture

The feature remains entirely in the web layer. Retained `ContentBlock`s and the
immutable Scout result enter a pure Scout trace adapter. That adapter emits the
shared `DocumentAnnotation[]` consumed by `DocumentTraceViewer`.

The adapter is a pure function. It may select, label, group, and reference
existing result objects, but it may not infer facts or mutate the result. The
viewer knows only the shared annotation contract and `ContentBlock`; it does not
import Scout types.

## Shared annotation contract

Each annotation contains only presentation and lineage references:

- stable annotation ID derived from existing result identity;
- one annotation kind from a small display vocabulary;
- title and short existing-result summary;
- exact existing block IDs;
- zero or more exact quotes already carried by the result;
- optional status text already carried by the result;
- a typed payload reference used by the tool-specific inspector; and
- source result identity for deterministic selection.

Annotations do not become part of exported JSON. The canonical authorities
remain the result object and retained blocks.

## Scout adapter

The Scout adapter projects these existing layers when they have document
lineage:

- canonical fields and document targets;
- reviewed quantitative targets;
- evidence relationships;
- grounding assessments;
- quantitative calibration results; and
- precedent assessments.

Queries, Findings, and source-only projections are shown in the selected
annotation details when reachable through the existing result, but they do not
highlight document text unless they already cite a document block.

The adapter deduplicates repeated annotations by existing identity and block
lineage. It never merges semantically distinct result records.

## Reading view

Blocks render in ordinal order within each source document. Headings,
paragraphs, lists, tables, and images use quiet document typography. The
reading canvas is one centered composition containing a narrow provenance
gutter and one continuous paper surface. The paper is not a collection of
block cards or UI rows: block boundaries have no dividers, outlines, repeated
paper edges, or artificial gaps.

Highlight behavior is provenance-sensitive:

- exact quote plus block ID: highlight the exact matching text;
- block ID without an exact quote: show a subtle marker in the document margin;
- unresolved block ID: retain the annotation in an unavailable group and do
  not attach it to unrelated content.

Highlights use one neutral base style. Selection and annotation kinds are
communicated with text and icons in the inspector, not color alone.

## Interaction

The view uses a two-pane layout where space permits:

- document reading pane;
- stable inspector pane for the selected annotation.

On smaller containers, the inspector opens as a sheet. Selecting highlighted
text, a margin marker, or an item in the annotation index selects the same
annotation. Multiple annotations on one passage appear as an ordered list
rather than overlapping highlight colors.

Filters control which existing Scout layers are visible. Filtering never
changes the underlying result or deletes annotations. Selection falls back to
the nearest visible annotation when its current item is filtered out.

Keyboard users can move between annotated passages, open details, return to the
document, and close the mobile sheet. Reduced-motion preferences disable scroll
and selection animation.

### Block navigation

Existing source controls may open the exact retained block in this view. The
navigation request contains only a canonical block ID; it does not create an
annotation, infer a source span, or change result data. Scout switches to the
Document trace tab, selects the source document that owns the block, scrolls the
retained block into view, and temporarily emphasizes the corresponding source
content.

Each retained block has a quiet, non-interactive gutter label showing its
compact block suffix (for example, `b-0089`). The full canonical ID remains
available through the label's accessible description and tooltip; the gutter
label has no implicit clipboard action. The selected destination temporarily receives a uniform solid
surface emphasis without an inset stripe, gradient, border, or artificial block
card. On containers narrower than `640px`, the gutter metadata moves above its
source block because a separate rail can no longer fit without compressing the
document.

The gutter and paper share one centered outer canvas, so the narrower gutter and
larger paper move and resize as a single visual unit. The gutter is navigation,
not an annotation index. Block-level connections are collapsed by connection
reason into at most two compact count controls per block. Activating a count
opens the existing inspector, where individual saved result records appear as
an ordered, scrollable list with layer and title. Exact-span annotations remain
attached to their source text. This progressive disclosure prevents repeated
layer labels from displacing the document while preserving every annotation ID
and its connection reason.

Each gutter label aligns with the first visible line of its corresponding
source block. Inter-block spacing is owned by the shared grid row rather than
independent top padding or margins in the gutter and paper columns, preventing
the two sides from drifting vertically across headings, paragraphs, and table
rows.

The shared viewer accepts a navigation request and reports when it has consumed
it. Scout owns tab selection and supplies that request; the generic viewer does
not know about Scout tabs or result types. `DocumentSourceTrace` exposes an
optional `Open in document trace` action only when a caller supplies the
navigation callback.

## Stability and failure handling

- Annotation construction is deterministic and order-preserving.
- Rendering never writes to result or session state.
- Exact-quote matching normalizes display-only whitespace; it does not validate
  or reinterpret provenance.
- A quote that cannot be located falls back to its valid block marker rather
  than highlighting approximate text.
- Missing blocks are reported honestly as unavailable.
- All blocks remain in document order and searchable. CSS
  `content-visibility: auto` may defer off-screen painting without removing
  blocks, annotations, or lineage from the document tree.

## Testing

Pure adapter tests cover:

- projection of every supported Scout layer;
- exact preservation of block IDs and quotes;
- stable annotation IDs and ordering;
- deduplication without semantic merging;
- missing-block and missing-quote behavior; and
- immutability of input results.

Viewer tests cover:

- continuous block rendering without chunk outlines;
- one centered gutter-and-paper canvas with no per-block separators;
- non-interactive gutter IDs and interactive linked-result counts;
- exact highlight and block-marker fallbacks;
- selection synchronization between document and inspector;
- layer filtering;
- keyboard interaction and accessible names; and
- responsive inspector behavior.

Production verification includes the full Python suite, every web `test:*`
script, TypeScript checking, the production web build, and `git diff --check`.

## Acceptance criteria

- Users can read a reconstructed source document and identify every displayed
  Scout result that cites each passage.
- The feature derives no new analytical data and changes no final-result
  contract.
- The Evidence map remains unchanged and complementary.
- The shared viewer contains no Scout-specific logic.
- Imported current Scout results work without recalculation or rerunning Scout.
- Existing source controls can jump to their canonical retained block in the
  Document trace without creating new lineage.
