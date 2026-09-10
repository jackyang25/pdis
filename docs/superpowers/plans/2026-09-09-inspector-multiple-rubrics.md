# Inspector Multiple Rubrics Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development for the backend task and integration review. No commits or pushes: the user's explicit instruction overrides skill commit steps.

**Goal:** Ship one document run containing independently identified PDID-template and applicable ICH-derived reviews.

**Architecture:** Preserve the existing per-unit assessment core; separate profile selection and rubric metadata from document preparation. New run results own blocks once and contain peer-level reviews. The same renderer and trace projection consume a selected review without hiding the other reviews from export or Assistant.

**Tech Stack:** Python 3.11, dataclasses/Pydantic, YAML, Next.js/React/TypeScript.

**Spec:** docs/superpowers/specs/2026-09-09-inspector-multiple-rubrics-design.md

## Global Constraints

- No commits, staging, pushing, or unrelated homepage edits. Work in the current checkout as the user requested.
- BMGF content and one-unit-per-request behavior remain unchanged.
- DOCX/PPTX only; source blocks and images retained once.
- Explicit yes/no/unknown product facts; no inference from indication.
- Whole-document guideline scope is not a physical document-section mapping.
- Source revisions and PDIS rubric revisions are distinct; saved text is a snapshot.
- All definitions are authored PDIS adaptations, not ICH certification.
- Legacy conversion only at import boundaries, never current-run fallback.

## Shared result interface

The HTTP response remains `{inspection: ...}`. The inspection object retains doc_id,
org, source_type, intervention_class, indication, blocks, document_findings,
consistency_status, assessment_status; replaces root sections with reviews and adds
applicability_facts and rubric_resolutions.

```typescript
type ProductFact = "yes" | "no" | "unknown";
type RubricSource = {id: string; title: string; revision: string; url: string};
type RequirementSnapshot = {
  id: string; section_name: string; variable_name: string | null;
  description: string; expectations: string; source_refs: string[];
};
type RubricSnapshot = {
  id: string; revision: string | null; display_name: string; authority: string;
  scope: string; stage_guidance: string; mirrors: string | null;
  evidence_scope: "mapped_section" | "whole_document";
  sources: RubricSource[]; requirements: RequirementSnapshot[];
};
type InspectionReview = {
  rubric: RubricSnapshot; sections: SectionAssessment[]; assessment_status: "complete";
};
type RubricResolution = {
  rubric_id: string; display_name: string;
  status: "included" | "outside_review_scope" | "needs_context";
  reason_code: string; reason: string;
};
```

Whole-document sections have `is_present: null`, `mapped_block_ids: []`; their unit
citations are validated against retained document IDs, not this empty physical mapping.
Assessment IDs in fresh runs are prefixed with rubric ID followed by `::`.
Product-fact keys are small_molecule, systemic_exposure, antiarrhythmic.
Frontend may derive a selected-review projection with sections and shared blocks for
existing viewers; this is never stored as a second result or exported.

## Task 1: Backend profiles, rubrics, assessment run and transport

**Files:** services/inspector/{configuration.py,models.py,pipeline.py,contract.py,assembly.py,__init__.py,configs/**,stages/assessor.py}; api/{operations/inspector.py,routes/inspector.py,schemas.py}; tests/test_inspector*.py; service CLI and config-catalog consumers as necessary.

**Consumes:** current BMGF files and Chunker's public API.
**Produces:** the shared response above and exported config/fact catalogs for input controls.

- [x] Test profile lookup and strict product-fact validation before implementing.
  Examples: missing three facts yields E14 needs_context; one disqualifying fact
  yields outside_review_scope; yes/yes/no yields included; invalid fact raises.
- [x] Test BMGF content equality and independent guideline evidence under Other.
  Reuse real schema-bound fake clients, not source-text assertions.
- [x] Implement strict configuration loading with pinned profiles/rubrics, explicit
  source metadata and source-referenced adapted requirements. Preserve BMGF YAML text.
- [x] Implement whole-document evidence mode in the existing assessor and contract.
  Unit absence cannot depend on a guideline section matching a Chunker label.
- [x] Implement parse-once orchestration, one consistency pass, snapshot assembly,
  qualified IDs and strict aggregate validation. Do not omit a failed included review.
- [x] Add the API operation and make transport delegate to it. Product facts arrive
  as `applicability_facts` JSON form text with explicit validation before running.
- [x] Publish relevant context-field definitions through the config endpoint, based
  on the selected profile rather than frontend E14 conditionals.
- [x] Run backend Inspector/config/route tests and full backend suite.

## Task 2: Portable result, viewer, trace and Assistant integration

**Files:** web/lib/{api.ts,result-file.ts,inspector-*.ts}; web/app/inspector/page.tsx; web/components/inspector-document-trace.tsx; shared Assistant adapters/legends and tests as required.

**Consumes:** shared response from Task 1.
**Produces:** single/multiple-review UI, versioned export and readable legacy import.

- [x] Add import/export fixtures for new multi-review payload and historical single
  review. Assert every rubric and image survives roundtrip; legacy revision is null.
- [x] Add frontend types and pure selected-review projection; migrate consumers
  without persisting a second flattened result.
- [x] Increment only Inspector analysis version; wrap compatible v2 results once
  at import. Pre-v2 semantics remain refused. Validate the current multi-review shape.
- [x] Render review selector above peer-level review content, sources and scope.
  Reuse SectionsList and annotation viewer with namespaced identities.
- [x] Show explicit unresolved/outside-scope resolutions; generate product-fact
  controls from the catalog with the existing ConfigField and Select components.
- [x] Scope priority/digest cache by rubric; retain document consistency once and
  all reviews in Assistant's context.
- [x] Run frontend tests, typecheck, build and desktop/mobile import interactions.

## Task 3: Integration review and documentation

- [x] Read final diff against the spec; independently review applicable-scope rules,
  enum/schema parity, source provenance, import boundaries and all consumers.
- [x] Update Inspector README, config template/docs generators and invariant text
  where the changed contract makes existing descriptions false. Preserve unrelated edits.
- [x] Run full backend/frontend verification and browser fixture review.
- [x] Leave all source edits uncommitted. Report exact verified scope and limits.

## Execution record

- Approved by user: build the whole flow, review afterward.
- Worktree ruling: work in place and retain changes, per user's explicit preference.
- Parallel boundary: one backend implementation agent; root owns frontend and
  portable-result integration. No overlapping file edits without a handoff.
- Interface review: Task 1 publishes review/scope snapshots; Task 2 consumes exactly
  those names. Task 3 checks both sides. No independent guideline enum in UI.

### Final verification and handoff

- Tasks 1–3 implemented. Existing BMGF content files remain unchanged; rubric
  metadata references them rather than moving or copying their content.
- Independent frontend and backend reviews completed; findings addressed in shared
  presentation, import validation, operation ownership and source-reference checks.
- Backend full suite: 1,111 tests, OK with one skip. Frontend: 651 tests passed.
- Production frontend build, including type validation, passed. `git diff --check`
  passed. No live model assessment was used for these checks.
- Browser fixture verified peer selection, shared sections, requirement disclosure,
  whole-document presence semantics, passage navigation and complete export at
  1440, 768, 375 and 320px. No horizontal overflow or browser script errors.
- Compatible v2 import, current multi-review roundtrip and retained image bytes are
  regression-tested. Historical revisions and requirements are not fabricated.
- ICH content is explicitly scoped, source-cited PDIS-authored adaptation; domain
  expert review and live assessment calibration remain separate from software tests.
- No changes staged, committed or pushed. Existing staged homepage/catalog work
  remains intact.

### Configuration naming cleanup

- Input profiles remain keyed by organization, document type and intervention.
- Template requirements now live under `rubrics/pdid/` with `pdid-...yaml`
  filenames; ICH definitions live under `rubrics/ich/`. All 20 moved YAML files
  retain byte-identical contents, including saved identifiers and input keys.
- Public document-config lookup now follows profile references in
  `configuration.py`, not organization-derived filenames in `models.py`.
- A regression test substitutes an independently named rubric and verifies lookup,
  availability and missing-profile behavior. Shared vocabulary checks use public
  catalogs rather than parsing filenames. Published prompt-reference output is
  unchanged.

### Shared assessment scheduling

- Replaced sequential rubric runs and nested section/unit pools with one
  interleaved unit queue using `shared.batching.map_ordered`, capped at 24 active
  calls per document run (the former maximum of four pools with six workers).
- Single-rubric assessment delegates to that same scheduler. Evidence formatting
  is reused, prompts are unchanged, and retries remain inside the worker limit.
- Progress reports one monotonic all-unit count. Ordered assembly retains rubric
  and unit order; failures prevent publication and the later consistency pass.
- Concurrency/progress/failure tests passed; a forced reversed-completion test
  protects authored unit ordering. Independent scheduling review found no blockers.
- Full backend suite: 1,116 tests run, OK with one skip before the additional
  reversed-completion test. Published prompt-reference output remains unchanged.
