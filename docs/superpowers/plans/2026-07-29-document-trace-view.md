# Document Trace View Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task by task. Execute in the current checkout, preserve unrelated work, and verify each task before proceeding.

**Goal:** Add a read-only Scout document view that reconstructs retained `ContentBlock`s into a continuous reading surface and connects exact passages—or block-level lineage when no exact passage exists—to the immutable analysis already stored in the result.

**Architecture:** Keep the feature entirely in `web/`. A pure generic trace module turns blocks plus generic annotations into a display model; a pure Scout adapter projects existing field, target, relationship, grounding, calibration, and precedent lineage into that contract; a shared viewer renders the document and selection inspector; a thin Scout component supplies labels and result-specific details. No service, API, result-envelope, import/export, or calculation contract changes.

**Tech Stack:** Next.js 14, React 18, TypeScript, Tailwind CSS, Lucide, Node's built-in test runner.

## Global constraints

- Treat the imported/final Scout result as immutable input. Never recalculate or amend it.
- Derive no new claim, status, summary, score, citation, or provenance edge.
- Exact source quotes may be highlighted after whitespace/case normalization only; do not use fuzzy matching.
- When a result has block lineage but no exact source quote, show a block-level margin marker rather than inventing a span.
- Keep `DocumentSourceTrace` and the Evidence map unchanged; the new view is complementary.
- Keep the shared viewer free of Scout types and vocabulary.
- Render every retained block in document order. Visual virtualization may defer painting but must not omit searchable content.
- Preserve image block bytes and block IDs already contained in `ContentBlock`.
- Use text labels in addition to color, keyboard-operable annotations, visible focus, Escape-to-close on the mobile inspector, and reduced-motion-safe scrolling.

---

### Task 1: Define the generic, immutable document-trace read model

**Files:**
- Create: `web/lib/document-trace.ts`
- Create: `web/lib/document-trace.test.ts`
- Modify: `web/package.json`

**Contract:**

```ts
export type DocumentAnnotation<TKind extends string = string, TRef = unknown> = {
  id: string;
  kind: TKind;
  layerLabel: string;
  title: string;
  summary: string;
  statusLabel?: string;
  blockIds: string[];
  quotes: string[];
  sourceRef: TRef;
};

export type DocumentTraceSegment = {
  text: string;
  annotationIds: string[];
};

export type DocumentTraceBlock<TKind extends string = string, TRef = unknown> = {
  block: ContentBlock;
  segments: DocumentTraceSegment[];
  markerAnnotations: DocumentAnnotation<TKind, TRef>[];
};
```

- `buildDocumentTrace(blocks, annotations)` sorts blocks by `doc_id`, then `ordinal`, finds exact quote ranges within only the annotation's declared blocks, unions overlapping annotation IDs, and places unmatched/block-only annotations in `markerAnnotations`.
- Matching may normalize whitespace, case, and HTML entities for locating display spans, but emitted segment text must remain the original block text.
- Unknown block IDs remain absent from the display model; the adapter/tests retain enough information for the inspector to say the source block is unavailable.
- Inputs are never mutated.

- [ ] **Step 1: Write failing pure-function tests**

Cover exact matches, whitespace/case normalization, no fuzzy fallback, overlapping annotations, marker fallback, multiple documents and stable order, filter behavior, unknown block IDs, and deep input immutability.

- [ ] **Step 2: Run the focused test and confirm failure**

```sh
npm --prefix web run test:document-trace
```

Expected: FAIL because the module and script do not exist.

- [ ] **Step 3: Implement the smallest generic read model**

Use a normalized-character index map to locate a normalized quote while returning offsets into original text. Merge range boundaries deterministically, then emit original-text segments. Add `filterDocumentAnnotations` as a pure helper.

- [ ] **Step 4: Run the focused test and require PASS**

```sh
npm --prefix web run test:document-trace
```

- [ ] **Step 5: Commit the generic model**

```sh
git add web/lib/document-trace.ts web/lib/document-trace.test.ts web/package.json
git commit -m "feat: add document trace read model"
```

---

### Task 2: Project Scout's existing lineage into generic annotations

**Files:**
- Create: `web/lib/scout-document-trace.ts`
- Create: `web/lib/scout-document-trace.test.ts`
- Modify: `web/package.json`

**Scout-only kinds:**

```ts
export type ScoutDocumentTraceKind =
  | "field"
  | "quantitative_target"
  | "relationship"
  | "grounding"
  | "calibration"
  | "precedent";
```

**Projection rules:**

- `Variable.document_spans` supplies exact field highlights; `Variable.block_ids` is fallback lineage.
- `QuantitativeTarget.provenance_spans` and `quote` supply exact target highlights; `doc_block_ids` is fallback lineage.
- `Match.doc_block_ids`, `EvidenceAssessment.doc_block_ids`, `Conformity.doc_block_ids`, and `PrecedentSignal.doc_block_ids` become block markers because those contracts do not claim exact document spans.
- Stable IDs use authoritative existing IDs where present (`target.id`, `insight.id`) and deterministic type/ref composites otherwise.
- Annotation summaries are copied from already-persisted result fields (`reason`, `verdict`, `document_target`, target expression); the adapter does not synthesize prose.
- Do not create annotations for records with neither valid block lineage nor exact spans.

- [ ] **Step 1: Write failing Scout-adapter tests**

Use a minimal typed fixture to assert all six layers, stable IDs/order, exact quotes only for the two source-span-owning layers, block-marker fallback for the other layers, multi-field conformity projection, records without lineage omitted, and no mutation of the result.

- [ ] **Step 2: Run both trace tests and confirm the adapter test fails**

```sh
npm --prefix web run test:document-trace
```

- [ ] **Step 3: Implement the pure Scout adapter**

Keep display label helpers local to the Scout adapter or reuse `displayAttributeLabel` through its public module. Return only `DocumentAnnotation<ScoutDocumentTraceKind, ScoutDocumentTraceRef>[]`.

- [ ] **Step 4: Run the focused tests and require PASS**

```sh
npm --prefix web run test:document-trace
```

- [ ] **Step 5: Commit the adapter**

```sh
git add web/lib/scout-document-trace.ts web/lib/scout-document-trace.test.ts web/package.json
git commit -m "feat: map scout lineage to document trace"
```

---

### Task 3: Build the shared continuous document viewer

**Files:**
- Create: `web/components/document-trace-viewer.tsx`

**Component boundary:**

```ts
type DocumentTraceViewerProps<TKind extends string, TRef> = {
  blocks: ContentBlock[];
  annotations: DocumentAnnotation<TKind, TRef>[];
  layers: Array<{ value: TKind; label: string }>;
  renderInspector: (annotation: DocumentAnnotation<TKind, TRef>) => ReactNode;
};
```

**Behavior:**

- Render a restrained toolbar with document selector when multiple `doc_id`s exist, layer filter, and annotation count.
- Render blocks as one continuous `<article>` with semantic heading/paragraph/image treatment and no block cards or visible block IDs.
- Exact-span annotations are inline keyboard-operable highlights. Block-only annotations are compact labeled margin buttons aligned to the relevant passage.
- Selecting an annotation opens a stable inspector at the right on large screens and a fixed bottom sheet on small screens. The small-screen sheet has a close button, Escape handling, focus return, an accessible dialog label, and a non-color-only selection state.
- If several annotations share a passage, show their labeled choices in the inspector without merging their meaning.
- Use `content-visibility: auto` and an intrinsic size hint on block wrappers; do not remove blocks from the DOM.
- Use restrained transitions and respect `prefers-reduced-motion` when scrolling a selected source into view.
- Empty states distinguish “no retained source document” from “no annotations for this layer.”

- [ ] **Step 1: Implement the viewer against the tested pure read model**

Do not import `ScoutResponse` or Scout label maps. Keep selection state local and reset it only when the selected annotation is no longer visible.

- [ ] **Step 2: Verify component typing**

```sh
npm --prefix web run typecheck
```

- [ ] **Step 3: Commit the shared viewer**

```sh
git add web/components/document-trace-viewer.tsx
git commit -m "feat: add continuous document trace viewer"
```

---

### Task 4: Add the Scout inspector and result-page tab

**Files:**
- Create: `web/components/scout-document-trace.tsx`
- Modify: `web/app/scout/page.tsx`

**Behavior:**

- Add `Document trace` after `Evidence map` in the existing result tabs.
- The Scout wrapper builds annotations with `useMemo`, supplies the six layer labels, and renders persisted result detail in the inspector.
- Inspector content shows layer, title, persisted status, persisted summary/reason, source passage availability, and a `DocumentSourceTrace` action using only the annotation's existing block IDs and quotes.
- Keep the Fields, Landscape, Safety, Evidence map, final actions, attributions, and `DocumentSourceProvider` behavior unchanged.
- Imported current results work immediately; no rerun or recalculation control is introduced.

- [ ] **Step 1: Add the thin Scout composition component**

The wrapper may import Scout types and `DocumentSourceTrace`; the generic viewer may not.

- [ ] **Step 2: Integrate one new result tab**

Keep tab ordering and responsive overflow behavior consistent with the existing Tabs primitives.

- [ ] **Step 3: Run focused and static verification**

```sh
npm --prefix web run test:document-trace
npm --prefix web run typecheck
npm --prefix web run build
```

- [ ] **Step 4: Commit the UI integration**

```sh
git add web/components/scout-document-trace.tsx web/app/scout/page.tsx
git commit -m "feat: add scout document trace view"
```

---

### Task 5: Cross-check provenance, accessibility, and repository health

**Files:**
- Modify only if verification exposes a real defect in the files above.

- [ ] **Step 1: Audit the implementation against the approved spec**

Confirm: continuous document reading; all blocks retained; exact highlights only; marker fallback; six filters; stable inspector; image rendering; no API/result changes; no newly generated content; no Evidence map or source-popover regression.

- [ ] **Step 2: Scan for placeholders and contract leaks**

```sh
rg -n "TODO|FIXME|placeholder|ScoutResponse" web/components/document-trace-viewer.tsx web/lib/document-trace.ts
git diff --check
```

Expected: no placeholders, no Scout import in the generic files, no whitespace errors.

- [ ] **Step 3: Run every web test script**

```sh
for script in $(node -e 'const p=require("./web/package.json"); console.log(Object.keys(p.scripts).filter(k=>k.startsWith("test:")).join(" "))'); do npm --prefix web run "$script"; done
```

- [ ] **Step 4: Run full required verification**

```sh
python -m compileall api services shared tests
python -m unittest discover -s tests
npm --prefix web run typecheck
npm --prefix web run build
git diff --check
```

- [ ] **Step 5: Review final diff and commit any verified corrections**

```sh
git status --short
git diff --stat
git diff -- web/lib/document-trace.ts web/lib/scout-document-trace.ts web/components/document-trace-viewer.tsx web/components/scout-document-trace.tsx web/app/scout/page.tsx web/package.json
```

Do not claim completion unless all applicable commands pass. Report any pre-existing failure separately from feature regressions.

---

### Task 6: Link existing source controls to canonical trace blocks

**Files:**
- Modify: `web/components/document-source-trace.tsx`
- Modify: `web/components/document-trace-viewer.tsx`
- Modify: `web/components/scout-document-trace.tsx`
- Modify: `web/app/scout/page.tsx`
- Test: `web/lib/document-trace.test.ts`

**Interfaces:**
- `DocumentSourceProvider` accepts optional
  `onOpenInTrace?: (blockId: string) => void`; every nested
  `DocumentSourceTrace` consumes that shared action without Scout-specific
  prop drilling.
- `DocumentTraceViewer` accepts optional `focusBlockId?: string` and
  `onFocusBlockConsumed?: (blockId: string) => void`.
- Scout owns the controlled result tab and pending canonical block ID. The
  shared source popover and trace viewer never import Scout types.

- [x] **Step 1: Write a failing pure helper test**

Add `compactBlockId(blockId)` coverage for canonical IDs, opaque IDs, and empty
values. This helper is the only transformation applied to gutter display text;
the complete ID remains the navigation authority.

- [x] **Step 2: Run the focused test and confirm the expected failure**

```sh
npm --prefix web run test:document-trace
```

- [x] **Step 3: Implement canonical block navigation**

Add the compact gutter control, deterministic block lookup, focus/scroll
handling, and the optional source-popover action. Use native buttons, visible
focus, `aria-label` with the full block ID, and instant scrolling when reduced
motion is requested.

- [x] **Step 4: Wire controlled Scout tabs without changing result data**

Replace the result Tabs' `defaultValue` with local controlled state. The source
popover callback sets the pending block ID and selects `Document trace`; the
viewer consumes that ID after focusing the exact retained block.

- [x] **Step 5: Verify the extension**

```sh
npm --prefix web run test:document-trace
npm --prefix web run typecheck
docker compose build web
git diff --check
```

### Task 6: Separate the block gutter from the annotation hierarchy

- [x] Group block-level markers by their existing connection reason without
  changing annotation IDs, order, or unmatched excerpts.
- [x] Keep the compact block ID as the quiet editor-style gutter control and
  replace repeated annotation chips with grouped connection counts.
- [x] Present individual connected records in the existing inspector as a
  scrollable layer-and-title list.
- [x] Preserve exact inline highlights and all canonical result data.
