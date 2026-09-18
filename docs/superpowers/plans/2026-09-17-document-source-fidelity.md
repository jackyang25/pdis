# Document Source Fidelity Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development or superpowers:executing-plans to implement task-by-task. Preserve pre-existing staged changes. Do not commit or push implementation changes without user direction.

**Goal:** Preserve meaningful source content with explicit extraction coverage and coherent shared citation/trace behavior.

**Architecture:** Keep ContentBlock identities and smaller analysis units. Slide/page metadata groups source content and one overview visual. Format-aware parsers own extraction; shared readers own coverage notices and citation mechanics; tools keep their authority and validation requirements.

**Tech Stack:** Python 3.11, python-docx, python-pptx, pypdf, PDFium, LibreOffice, TypeScript/React.

**Spec:** `docs/superpowers/specs/2026-09-17-document-source-fidelity-design.md`

**Execution record:** Implementation and review outcomes are recorded in
`.superpowers/sdd/2026-09-17-document-source-fidelity/progress.md`. Changes remain
local and uncommitted at the user's request. The supplied PDF/PPTX were parsed
and inspected without AI calls. The named saved Screener JSON was unavailable at
final verification; legacy import behavior is covered by synthetic tests instead,
not claimed as a successful fresh reopen of that file.

## Global Constraints

- PDF remains Screener-only; DOCX/PPTX remain supported by other document tools.
- No OCR, inferred chart boundaries, reconstructed PDF tables, or AI-written source text.
- Source IDs belong to a saved run; never rewrite old provenance from a fresh parse.
- Visual references are not exact quotations; numeric-target text validation remains intact.
- No paid AI calls, deployment, pushing, or modifying user source documents.
- Pre-existing staged Scout changes remain staged and untouched except necessary additive integration reviewed explicitly.
- Worktree choice must be resolved before implementation because the current checkout is main.

## Task 1: Bounded rendering and explicit coverage

**Files:** `services/chunker/stages/rasterizer.py`, `parser_pptx.py`, `parser_pdf.py`, `shared/document_metadata.py`, `tests/test_chunker_pptx.py`, `tests/test_chunker_pdf.py`, new rendering tests.

**Interface:** Preserve `render_presentation_slides(file_path)` where practical; factor a shared PDF-page render operation using existing PDFium. Parser-authored warning codes live in structural metadata and resolve through one shared vocabulary. Do not add format-specific model interfaces.

- [ ] Add regressions proving fallback is observable in returned PPTX metadata and preserved by serialization.
- [ ] Add PDF visual regressions with a vector-only drawing on a text-bearing page: page text survives and exactly one full-page image is retained, not separately extracted picture fragments.
- [ ] Run tests and observe old implementation fail these expectations.
- [ ] Implement bounded PDFium page rendering; enforce positive dimensions, page count, per-page pixel budget and aggregate encoded-image budget before publishing a complete parse.
- [ ] Distinguish unavailable converter from failed conversion, and preserve existing PPTX picture fallback only with a warning. Keep PDF parse refusal semantics for malformed, encrypted, textless and over-limit sources.
- [ ] Update old PDF tests that intentionally pinned the replaced embedded-image-only path; retain all unrelated input safety tests.
- [ ] Run the extraction suite and repeated local rendering on the supplied PDF/PPTX. Inspect coverage/asset metadata and representative visuals, not count alone.

## Task 2: DOCX explicit content coverage

**Files:** `services/chunker/stages/parser_docx.py`, `image_assets.py`, new focused DOCX part-reader module if necessary, `tests/test_chunker_images.py`, new DOCX coverage tests.

**Interface:** Produce ordinary ContentBlocks with authored location/part metadata. Resolve image relationships within their owning package part, not always the body part. Do not invent document page numbers.

- [ ] Build synthetic DOCX fixtures with body text, floating text box, nested table, referenced footnote/endnote, header/footer text and an unsupported native visual object.
- [ ] Assert exact retained text, distinct stable identities, identified part locations, and no repeated text-box/body extraction.
- [ ] Observe failing coverage tests before implementation.
- [ ] Traverse explicit OOXML containers/relationships in authored order; retain referenced notes and identify headers/footers once per source part.
- [ ] Report unsupported meaningful objects rather than silently claiming complete extraction. Avoid broad descendant-text flattening and library-private display-order guesses.
- [ ] Run DOCX table/image regressions and validate portable serialization of newly covered parts.

## Task 3: Shared provenance and model context

**Files:** `shared/spans.py`, `shared/document_metadata.py`, source/context helpers in Inspector/Aligner/Scout/Screener, affected model schemas/contracts and tests.

**Interface:** Keep DocumentSpan exact-text semantics. Add visual references separately only where the tool accepts visual evidence; source IDs must resolve to retained assets. A `[image]` marker is not a meaningful quote.

- [ ] Add regressions for a real text selection, invalid text range, missing visual asset, visual-only Aligner support, and refusal to pass a visual marker as an exact numeric-target quotation.
- [ ] Observe expected failures before modifying schemas/consumers.
- [ ] Reuse shared membership/range resolution and coverage descriptions. Keep verdict/state rules owned by tools.
- [ ] Include same-slide overview context for Inspector's mapped blocks without reclassifying all slide text into one section; citations validate against the actual supplied block collection.
- [ ] Carry extraction warnings and same-source identity into model context, including Assistant; preserve complete saved source collections.
- [ ] Update analysis-version/import handling for changed citation shapes, without fabricated historical references. Test fresh and saved-result contracts.

## Task 4: Shared trace and citation presentation

**Files:** `web/lib/document-trace-surfaces.ts`, `web/lib/document-extraction.ts`, shared document trace/source components, extraction notice, shared result readers and tests.

**Interface:** Group by declared slide/page only. DOCX remains flow-based. Cited text remains addressable even when visually secondary. No browser reparsing or inference of missing historical coverage.

- [ ] Add render/navigation regressions for slide/page overview labeling, retained-text disclosure, citation revealing its text, historical picture-only results, warnings and visual-only references.
- [ ] Observe failures before implementation.
- [ ] Reuse shared UI primitives for a clearly named slide/page visual and extracted text. Preserve block IDs and source-list navigation.
- [ ] Provide an accessible larger view for dense visuals, with keyboard close/focus restoration and no loss of citation context.
- [ ] Display shared extraction notices in all relevant result/source readers, including imports. Do not synthesize a warning for older PPTX files lacking coverage metadata.
- [ ] Run web tests/typecheck and desktop/narrow keyboard browser checks.

## Task 5: Integration, documentation, and review

**Files:** affected service READMEs, `shared/product_knowledge.json`, `AGENTS.md` PDF policy, generated prompt reference/snapshot if prompts change, release notes only if materially needed.

- [ ] Remove superseded paths only after their replacement regressions pass; search all public source/citation consumers for old assumptions.
- [ ] Update documentation to describe coverage guarantees and limits accurately, including no inferred pixel highlights and no claim of semantic correctness from quote matching.
- [ ] Run full backend tests, lint, web tests, typecheck and build where available. Distinguish unrelated baseline failures from introduced ones.
- [ ] Reopen the supplied saved result unchanged; verify legacy fidelity. Parse supplied source files afresh and inspect the new trace without AI calls.
- [ ] Independent code review of extraction, provenance and UI integration; address consequential findings before handoff.
- [ ] Report exact checks, remaining limitations and rerun requirements. Do not claim paid/live AI validation occurred.

## Preflight interface review

| Tasks | Shared boundary | Resolution |
|---|---|---|
| 1 / 2 / 3 / 4 | Extraction warnings | Parser authors facts; shared vocabulary translates; readers never diagnose historical missing content. |
| 1 / 3 / 4 | Overview visuals | Existing block/image identity; same slide/page is a context relation, not independent evidence. |
| 2 / 3 | New DOCX parts | Ordinary content blocks with explicit part location and correct image relationship owner. |
| 3 / 4 | Visual citation | Distinct from text spans; no quotation marker substitutes for source prose. |
| 3 / 5 | Portable schema | Version/import policy must preserve or refuse old guarantees, never silently migrate meaning. |

Each task has a behavior-first regression boundary. Task 3 must finish its schema decisions before Task 4 consumes them. No implementation is marked complete solely from asset counts or passing existing tests.
