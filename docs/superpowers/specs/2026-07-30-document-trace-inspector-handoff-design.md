# Document Trace Inspector Handoff Design

## Goal

Make source citations and document-trace results feel like one coherent workflow without merging their responsibilities or creating nested overlays.

## Responsibilities

### Source passage preview

`DocumentSourceTrace` is the lightweight citation preview used from result pages. It answers: “What retained source passage supports this result?” It may switch among cited passages, show exact cited text and surrounding retained content, expose the canonical block ID, and navigate to the reconstructed document.

It must not list downstream result layers or open a second result inspector. When navigation begins, it closes before changing views.

### Document trace inspector

`DocumentTraceViewer` owns exploration inside the reconstructed document. It answers: “Which saved results connect to this passage, and how?” It shows a stable connected-results list when multiple annotations share a passage and a single selected-result detail hierarchy below it.

The trace inspector must not embed `DocumentSourceTrace`; the source passage remains visible and selected in the document beside the inspector. The inspector presents only persisted result metadata and its connection type.

## Navigation Handoff

Selecting “Go to block” from a source preview:

1. closes the source preview;
2. opens the document-trace view;
3. switches to the source document that owns the exact block ID;
4. scrolls the block to the visual center and moves programmatic focus to it;
5. applies a temporary warm-yellow emphasis to the complete block;
6. opens the uniquely matching connected result when one can be identified without guessing;
7. otherwise leaves the block focused with its linked-result affordance available.

The handoff uses existing block and annotation IDs only. It does not infer, recalculate, or create provenance.

## Visual Hierarchy

### Shared inspector structure

Both the source preview and trace inspector use the same hierarchy where their content overlaps:

1. compact eyebrow describing the object type;
2. primary title;
3. one-sentence explanation or status;
4. main content;
5. restrained audit metadata and actions.

This structure is implemented with shared presentation primitives rather than duplicated card styling. The preview remains a compact popover; the trace remains a persistent desktop rail and an accessible narrow-screen sheet.

### Trace inspector details

The connected-results selector is a quiet list above the detail view, not a nested card stack. Each row exposes layer, title, and selected state. The selected detail contains:

- result layer and title;
- optional status;
- persisted result summary;
- connection-to-source explanation;
- source-passage counts or unmatched/unavailable details when applicable.

The connection section does not repeat source content or expose another “In document” control.

### Destination emphasis

The destination block uses the existing warm-yellow citation color as a solid translucent background with a restrained outline and halo. It must not use gray fill, a gradient, or a colored edge stripe. The emphasis fades after approximately two seconds. With reduced motion enabled, the block receives the same distinct static emphasis for the same period without animated scaling or pulsing.

Inline exact-citation highlights retain the same warm-yellow family so citation preview, trace selection, and navigation emphasis read as one system.

## Accessibility

- Preview navigation closes the popover and restores a predictable focus path before the trace receives focus.
- The focused block remains a programmatically focusable semantic section with a descriptive accessible label.
- Connected-result rows are native buttons with visible selected and focus states.
- Narrow-screen trace details retain the existing dialog semantics, focus trap, Escape behavior, and trigger focus restoration.
- Motion respects `prefers-reduced-motion`.
- Status and selection do not rely on color alone.

## Data Boundaries

- Source preview consumes retained `ContentBlock` records and exact spans.
- Trace navigation consumes canonical block IDs and, when supplied, an exact annotation ID.
- Trace inspector consumes existing `DocumentAnnotation` and `DocumentTraceConnection` values.
- No result contract, API schema, calculation, source block, or exported artifact changes.
- If a requested block or annotation is unavailable, the UI keeps the existing explicit unavailable state and never substitutes an approximate match.

## Verification

- Unit tests cover navigation intent, unique-result selection, ambiguous-result fallback, and emphasis presentation.
- Existing document-trace, Scout trace, block-reference, and evidence-map tests continue to pass.
- Keyboard checks cover opening and closing the preview, activating “Go to block,” selecting connected results, closing the narrow-screen sheet, and focus restoration.
- The Scout result page is checked at desktop width and at a narrow width for clipping, overlay nesting, and reading order.
- Run TypeScript typecheck, production web build, and `git diff --check`.
