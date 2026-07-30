# Document Trace Inspector Handoff Implementation Plan

> **For implementation:** Execute each task in order and keep the saved result contract unchanged.

**Goal:** Make source citations and document-linked results feel like one coherent trace without nesting or duplicating their responsibilities.

**Architecture:** `DocumentSourceTrace` remains a lightweight source-passage preview. `DocumentTraceViewer` remains the only owner of connected-result inspection. A tested trace-focus resolver selects a connected result only when one unambiguous annotation belongs to the destination block; otherwise it focuses the block without guessing. Shared presentation primitives keep both surfaces visually aligned while preserving their distinct roles.

**Tech stack:** React 18, Next.js 14, TypeScript, Radix Popover, Tailwind CSS, Node test runner.

## Task 1: Define the block-to-result handoff contract

**Files:**

- Modify: `web/lib/document-trace.ts`
- Modify: `web/lib/document-trace.test.ts`

1. Add failing tests for a uniquely connected exact annotation, a uniquely connected block-only annotation, an ambiguous block with multiple annotations, and an unknown block.
2. Run `npm --prefix web run test:document-trace` and confirm the new tests fail because the resolver does not exist.
3. Add a pure `documentTraceFocusTarget` resolver that returns document ownership and an optional unique annotation connection without inferring or merging records.
4. Re-run `npm --prefix web run test:document-trace` and confirm it passes.

## Task 2: Separate preview and inspection responsibilities

**Files:**

- Create: `web/components/document-trace-panel.tsx`
- Modify: `web/components/document-source-trace.tsx`
- Modify: `web/components/scout-document-trace.tsx`

1. Add a shared, restrained panel header/section primitive for trace surfaces.
2. Make the source popover controlled so “Open in document trace” closes it before navigation.
3. Keep the source popover limited to retained source content, exact cited text, audit identity, and the navigation action.
4. Remove the nested source popover from the Scout result inspector. Keep the inspector limited to saved-result meaning, connection status, and provenance counts.
5. Run `npm --prefix web run typecheck` to catch component contract drift.

## Task 3: Implement exact navigation and temporary destination emphasis

**Files:**

- Modify: `web/components/document-trace-viewer.tsx`

1. Consume `documentTraceFocusTarget` when an external block focus arrives.
2. Switch documents if necessary, scroll and focus the exact block, and open the result inspector only for a unique connected annotation.
3. Preserve block-only focus when the mapping is ambiguous rather than choosing a result.
4. Replace gray inline citations and destination styling with a restrained solid warm-yellow highlight.
5. Keep the arrival emphasis temporary, respect reduced motion, and restore keyboard focus when the narrow inspector closes.
6. Use the shared trace panel hierarchy in both the desktop inspector and narrow dialog without duplicating source content.
7. Run `npm --prefix web run test:document-trace` and `npm --prefix web run typecheck`.

## Task 4: Verify the integrated UI

**Files:**

- Review: all files changed above

1. Run `npm --prefix web run test:document-trace`.
2. Run `npm --prefix web run typecheck`.
3. Run `npm --prefix web run build`.
4. Run `git diff --check`.
5. Review the final diff for nested overlays, duplicate source content, guessed result selection, and unrelated changes.

