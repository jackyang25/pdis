# Document Trace Outer Gutter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render the document as one centered gutter-and-paper canvas with quiet provenance labels, linked-result controls outside the paper, and no artificial block-row separators.

**Architecture:** Extend the existing pure presentation helper with one container-width-based rail mode and a shared block-spacing vocabulary, then consume both in the shared document-trace viewer. The outer canvas centers the gutter and paper as one unit; the paper is one continuous surface behind source content only whenever the trace has at least `640px`. Canonical block IDs become non-interactive gutter labels, grouped persisted-result markers remain the only gutter actions, and the inspector independently collapses at `1024px`.

**Tech Stack:** TypeScript, React, Tailwind CSS, Node test runner

## Global Constraints

- Preserve canonical block text, order, IDs, annotations, result links, and inspector behavior.
- Do not add absolute per-block positioning, infer new connections, or modify result contracts.
- Desktop linked-result controls sit outside the paper; narrow layouts place the same metadata above block content.
- Block IDs are labels, not implicit clipboard actions.
- Block boundaries have no separators; hover and linked-result focus use one uniform solid overlay.
- A gutter label aligns with the first visible line of its source block.

---

### Task 1: Add and consume the responsive outer rail

**Files:**
- Modify: `web/lib/document-block-presentation.ts`
- Modify: `web/lib/document-block-presentation.test.ts`
- Modify: `web/components/document-trace-viewer.tsx`

**Interfaces:**
- Consumes: the viewer's existing `isNarrow` responsive state.
- Produces: `documentTraceRailMode(containerWidth: number): "inline" | "external"`.

- [x] **Step 1: Write the failing responsive-mode test**

```ts
test("places trace controls outside the paper only when space permits", () => {
  assert.equal(documentTraceRailMode(1024), "external");
  assert.equal(documentTraceRailMode(720), "external");
  assert.equal(documentTraceRailMode(639), "inline");
});
```

- [x] **Step 2: Run the focused test and confirm it fails because the helper is absent**

Run: `node --test --experimental-strip-types web/lib/document-block-presentation.test.ts`

- [x] **Step 3: Implement the minimal responsive-mode helper**

```ts
export function documentTraceRailMode(containerWidth: number): "inline" | "external" {
  return containerWidth >= 640 ? "external" : "inline";
}
```

- [x] **Step 4: Render the paper and rail as separate visual layers**

Use one continuous desktop paper backdrop behind the content column. Keep block IDs and grouped result controls in the left rail. Apply the block hover/focus surface to the content column and preserve the existing inspector actions.

- [x] **Step 5: Verify the focused tests**

Run: `npm --prefix web run test:document-trace`

- [x] **Step 6: Verify typechecking, production build, and diff hygiene**

Run: `npm --prefix web run typecheck`

Run: `npm --prefix web run build`

Run: `git diff --check`

---

### Task 2: Unify the centered canvas and remove row chrome

**Files:**
- Modify: `web/components/document-trace-viewer.tsx`
- Modify: `web/lib/document-block-presentation.ts`
- Modify: `web/lib/document-block-presentation.test.ts`

**Interfaces:**
- Consumes: `documentBlockPresentation(block): DocumentBlockPresentation` and the existing trace block/marker contract.
- Produces: `documentBlockSpacing(presentation): DocumentBlockSpacing`, used by the shared row so gutter and content receive one vertical rhythm.

- [x] **Step 1: Write failing tests for the shared block-spacing vocabulary**

Assert that headings, body content, and table rows map to stable spacing roles without adding per-row dividers.

- [x] **Step 2: Run the focused presentation test and verify the new helper is absent**

Run: `node --test --experimental-strip-types web/lib/document-block-presentation.test.ts`

- [x] **Step 3: Implement the minimal spacing helper**

Add a closed `DocumentBlockSpacing` union and map the existing presentation roles to it.

- [x] **Step 4: Rebuild the viewer row around one shared vertical rhythm**

Center one outer `gutter + paper` canvas. Remove the block-ID button, clipboard/check state, inline row divider, and per-block inset chrome. Render the compact ID as text, retain linked-result buttons, and align the gutter to the first visible source line.

- [x] **Step 5: Verify focused tests, TypeScript, production build, and diff hygiene**

Run: `npm --prefix web run test:document-trace`

Run: `npm --prefix web run typecheck`

Run: `npm --prefix web run build`

Run: `git diff --check`
