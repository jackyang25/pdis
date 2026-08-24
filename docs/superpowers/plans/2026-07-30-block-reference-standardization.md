# Block Reference Standardization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give Scout, Inspector, Aligner, and Evidence Map one compact, navigable, provenance-preserving block-reference presentation.

**Architecture:** Canonical block IDs remain unchanged in result data. A small presentation module derives compact visible IDs and accessible labels, shared source-passage UI owns passage inspection, and the document trace renders connection counts beside—not below—the gutter ID.

**Tech Stack:** Next.js, React, TypeScript, Tailwind CSS, Node test runner, Lucide icons.

## Global Constraints

- Do not change parsed blocks, API schemas, result envelopes, import/export, or provenance contracts.
- Full canonical IDs remain the lookup, navigation, tooltip, accessible-name, and copy values.
- Visible references use compact IDs such as `b-0040` without a visible `Block` prefix.
- User-facing copy uses `In document` and `Source passage`; `Block ID` appears only in audit detail.
  (The action read `View source` until an outward-facing counterpart, `Sources`, was added
  beside it in Scout - at which point neither label said which direction it pointed.)
- Do not render a navigation action unless a valid destination callback exists.
- Preserve the stateless client-held result lifecycle.

---

### Task 1: Shared block-reference presentation contract

**Files:**
- Create: `web/lib/block-reference.ts`
- Create: `web/lib/block-reference.test.ts`
- Create: `web/components/block-reference.tsx`
- Modify: `web/lib/document-trace.ts`
- Modify: `web/lib/document-trace.test.ts`
- Modify: `web/package.json`

**Interfaces:**
- Produces: `compactBlockId(blockId: string): string`
- Produces: `blockReferenceLabel(blockId: string): string`
- Produces: `sourcePassageAriaLabel(count: number): string`
- Produces: `BlockReferenceId({ blockId, className })`
- Consumes: complete canonical block IDs already carried by result contracts.

- [ ] **Step 1: Write failing presentation tests**

```ts
test("keeps the canonical ID while deriving one compact visible ID", () => {
  assert.equal(compactBlockId("DRAFT AIV/b-0040"), "b-0040");
  assert.equal(blockReferenceLabel("DRAFT AIV/b-0040"), "Source block ID DRAFT AIV/b-0040");
});

test("uses source-passage language for one and many references", () => {
  assert.equal(sourcePassageAriaLabel(1), "View 1 source passage");
  assert.equal(sourcePassageAriaLabel(3), "View 3 source passages");
});
```

- [ ] **Step 2: Run the tests and confirm the new module is missing**

Run: `npm --prefix web run test:block-reference`

Expected: FAIL because `web/lib/block-reference.ts` does not exist.

- [ ] **Step 3: Implement the pure presentation helpers**

```ts
export function compactBlockId(blockId: string): string {
  const compact = blockId.split("/").filter(Boolean).at(-1);
  return compact || "Unavailable";
}

export function blockReferenceLabel(blockId: string): string {
  return `Source block ID ${blockId}`;
}

export function sourcePassageAriaLabel(count: number): string {
  return `View ${count} source ${count === 1 ? "passage" : "passages"}`;
}
```

Move `compactBlockId` out of `document-trace.ts`, update imports, and replace its old empty-ID expectation with `Unavailable`.

- [ ] **Step 4: Add the shared visible-ID component**

```tsx
export function BlockReferenceId({ blockId, className }: BlockReferenceIdProps) {
  return (
    <span
      aria-label={blockReferenceLabel(blockId)}
      title={blockId}
      className={cn("font-mono tabular-nums", className)}
    >
      {compactBlockId(blockId)}
    </span>
  );
}
```

- [ ] **Step 5: Run the focused tests**

Run: `npm --prefix web run test:block-reference && npm --prefix web run test:document-trace`

Expected: PASS.

- [ ] **Step 6: Commit the shared contract**

```bash
git add web/lib/block-reference.ts web/lib/block-reference.test.ts web/components/block-reference.tsx web/lib/document-trace.ts web/lib/document-trace.test.ts web/package.json
git commit -m "refactor: centralize block reference presentation"
```

---

### Task 2: Compact the document-trace gutter

**Files:**
- Modify: `web/components/document-trace-viewer.tsx`
- Modify: `web/lib/document-trace.test.ts`

**Interfaces:**
- Consumes: `BlockReferenceId` and existing `groupDocumentTraceMarkers()` output.
- Produces: one baseline-aligned gutter row per reconstructed block.
- Preserves: existing `selectAnnotations()` behavior and the right-side annotation inspector.

- [ ] **Step 1: Add a failing marker-group assertion for compact count data**

```ts
assert.deepEqual(
  groupDocumentTraceMarkers(markers).map((group) => ({
    reason: group.reason,
    count: group.annotationIds.length,
  })),
  [
    { reason: "block_only", count: 2 },
    { reason: "quote_unmatched", count: 1 },
  ],
);
```

- [ ] **Step 2: Run the trace tests**

Run: `npm --prefix web run test:document-trace`

Expected: the new assertion fails until its fixture represents both marker groups.

- [ ] **Step 3: Render one horizontal gutter row**

Use a fixed-width external rail with `flex-row`, align it with the first content baseline, render `BlockReferenceId` first, and render each marker group as a compact icon-plus-count button. Keep verbose meaning in `aria-label` and `title`; do not put `linked results` or `unmatched excerpts` visibly in the gutter.

```tsx
<button aria-label={`View ${label} connected to ${traceBlock.block.id}`} title={label}>
  <Link2 aria-hidden="true" />
  <span className="tabular-nums">{group.annotationIds.length}</span>
</button>
```

Keep exact highlighted spans as the primary inline affordance and preserve the current active-state and inspector-opening behavior.

- [ ] **Step 4: Verify trace behavior and types**

Run: `npm --prefix web run test:document-trace && npm --prefix web run typecheck`

Expected: PASS.

- [ ] **Step 5: Commit the gutter change**

```bash
git add web/components/document-trace-viewer.tsx web/lib/document-trace.test.ts
git commit -m "refactor: compact document trace gutter references"
```

---

### Task 3: Reuse source-passage inspection across all tools

**Files:**
- Modify: `web/components/document-source-trace.tsx`
- Modify: `web/components/scout-document-trace.tsx`
- Modify: `web/components/scout-evidence-map.tsx`
- Modify: `web/app/inspector/page.tsx`
- Modify: `web/app/aligner/page.tsx`
- Modify: `web/lib/scout-evidence-map.test.ts`

**Interfaces:**
- Consumes: `DocumentSourceProvider`, `DocumentSourceTrace`, `sourcePassageAriaLabel()`, and canonical block IDs.
- Produces: the same `In document` affordance and `Source passage` inspector in Scout, Inspector, Aligner, and Evidence Map.
- Navigation: `Open in document trace` is emitted only when `DocumentSourceProvider` receives `onOpenInTrace`.

- [ ] **Step 1: Add a failing Evidence Map assertion that compact source references remain attached to nodes**

```ts
assert.deepEqual(
  projection.nodes.find((node) => node.id === "document:clinical_efficacy")?.blockIds,
  ["document/b-0007"],
);
```

The assertion protects provenance while the raw-ID text display is removed.

- [ ] **Step 2: Run the Evidence Map test**

Run: `npm --prefix web run test:evidence-map`

Expected: PASS before UI replacement, establishing that the canonical ID is already available to the shared source inspector.

- [ ] **Step 3: Normalize `DocumentSourceTrace` copy and IDs**

Use `sourcePassageAriaLabel()` for the trigger, `BlockReferenceId` in the audit footer, and retain the full ID as the copied value. Keep the visible action `In document`, the header `Source document`, and the audit label `Block ID`.

- [ ] **Step 4: Replace Inspector's local source-block details**

Wrap Inspector result tabs in `DocumentSourceProvider blocks={inspection.blocks}`. Replace `BlockTrace` with `DocumentSourceTrace`; remove the duplicated raw-ID/content renderer and its `blocksById` plumbing.

- [ ] **Step 5: Replace Aligner's local source-block details**

Wrap the alignment result in `DocumentSourceProvider blocks={result.blocks}`. Replace each `source block(s)` details element in `UnitSide` with `DocumentSourceTrace blockIds={unit.block_ids}` and remove the local block-map rendering.

- [ ] **Step 6: Replace Evidence Map raw block lists**

Render `DocumentSourceTrace blockIds={node.blockIds}` in the node inspector instead of the `Document blocks` heading and `join(" · ")` output. The existing Scout provider supplies retained blocks and trace navigation.

- [ ] **Step 7: Normalize remaining Scout trace copy**

Use `Source passage connection`, `source passage(s)`, and `cited passage(s)` in user-facing labels. Keep technical `blockId` property names unchanged.

- [ ] **Step 8: Audit visible vocabulary**

Run:

```bash
rg -n 'source block|Document blocks|Block [a-zA-Z0-9_-]*/b-|View [0-9]+ source block' web/app web/components
```

Expected: no user-facing mixed vocabulary remains outside the intentional audit label `Block ID`, accessible names, and implementation identifiers.

- [ ] **Step 9: Run focused and cross-page verification**

Run:

```bash
npm --prefix web run test:block-reference
npm --prefix web run test:document-trace
npm --prefix web run test:evidence-map
npm --prefix web run typecheck
npm --prefix web run build
git diff --check
```

Expected: all commands pass.

- [ ] **Step 10: Commit the cross-tool standardization**

```bash
git add web/components/document-source-trace.tsx web/components/scout-document-trace.tsx web/components/scout-evidence-map.tsx web/app/inspector/page.tsx web/app/aligner/page.tsx web/lib/scout-evidence-map.test.ts
git commit -m "refactor: standardize source passage references"
```
