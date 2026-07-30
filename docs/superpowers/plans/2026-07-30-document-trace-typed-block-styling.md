# Document Trace Typed-Block Styling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve document-trace scanning by styling canonical headings and table rows according to existing `ContentBlock` metadata.

**Architecture:** Add one pure presentation helper that maps a `ContentBlock` to a closed visual role, then consume that role in the existing shared document-trace renderer. The helper interprets only `block_type` and a valid numeric `structural_meta.heading_level`; source content, ordering, annotations, and analysis data remain unchanged.

**Tech Stack:** TypeScript, React, Tailwind CSS, Node test runner

## Global Constraints

- Do not parse table-row prose into cells or columns.
- Do not infer structure from `section_label`, arbitrary prose, parser coordinates, or source format.
- Preserve canonical block text, order, image bytes, IDs, highlights, annotations, and trace interactions.
- Do not change Chunker, API schemas, result envelopes, or analysis services.

---

### Task 1: Define and consume canonical block presentation roles

**Files:**
- Create: `web/lib/document-block-presentation.ts`
- Create: `web/lib/document-block-presentation.test.ts`
- Modify: `web/components/document-trace-viewer.tsx`
- Modify: `web/package.json`

**Interfaces:**
- Consumes: `ContentBlock` from `web/lib/api.ts`.
- Produces: `documentBlockPresentation(block: ContentBlock): "heading-primary" | "heading-secondary" | "heading-tertiary" | "table-row" | "body"`.

- [x] **Step 1: Write the failing tests**

```ts
test("maps canonical heading levels to a restrained hierarchy", () => {
  assert.equal(documentBlockPresentation(contentBlock("heading", { heading_level: 1 })), "heading-primary");
  assert.equal(documentBlockPresentation(contentBlock("heading", { heading_level: 2 })), "heading-secondary");
  assert.equal(documentBlockPresentation(contentBlock("heading", { heading_level: 4 })), "heading-tertiary");
});

test("falls back safely and preserves table rows as one visual record", () => {
  assert.equal(documentBlockPresentation(contentBlock("heading", {})), "heading-secondary");
  assert.equal(documentBlockPresentation(contentBlock("table_row", { row_index: 2 })), "table-row");
  assert.equal(documentBlockPresentation(contentBlock("paragraph", {})), "body");
});
```

- [x] **Step 2: Run the test to verify it fails**

Run: `node --test --experimental-strip-types web/lib/document-block-presentation.test.ts`

Expected: FAIL because `document-block-presentation.ts` does not exist.

- [x] **Step 3: Implement the minimal pure presentation mapping**

```ts
export type DocumentBlockPresentation =
  | "heading-primary"
  | "heading-secondary"
  | "heading-tertiary"
  | "table-row"
  | "body";

export function documentBlockPresentation(block: ContentBlock): DocumentBlockPresentation {
  if (block.block_type === "table_row") return "table-row";
  if (block.block_type !== "heading") return "body";
  const level = block.structural_meta.heading_level;
  if (typeof level !== "number" || !Number.isFinite(level)) return "heading-secondary";
  if (level <= 1) return "heading-primary";
  if (level === 2) return "heading-secondary";
  return "heading-tertiary";
}
```

- [x] **Step 4: Apply the roles in the shared renderer**

Use semantic heading elements and restrained size/spacing for the three heading roles. Render `table-row` as a single compact bordered row surface with tabular numerals; do not split or rewrite its content. Leave images and body paragraphs unchanged.

- [x] **Step 5: Run focused verification**

Run: `npm --prefix web run test:document-trace`

Expected: all document-trace and block-presentation tests pass.

- [x] **Step 6: Run full web verification**

Run: `npm --prefix web run typecheck`

Run: `npm --prefix web run build`

Run: `git diff --check`

Expected: every command exits successfully.
