# Scout Projection Roles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Scout's Landscape and Safety projections state each structured record's source-study role and relationship to the uploaded product without changing any canonical claim, retrieval, evidence, precedent, or quantitative result.

**Architecture:** Searcher adapters may add a closed `source_role` only from explicit provider metadata. Scout groups normalized records losslessly, assigns stable projection IDs, and runs one schema-bound OpenAI classification stage that enriches only the two derived projection arrays with `target_relationship`; failures remain `unknown` and never block the core run. The API, current final-result contract, Assistant vocabulary, and UI consume those persisted fields without recalculation.

**Tech Stack:** Python 3 dataclasses, strict JSON Schema model calls, Pydantic/FastAPI, Next.js 14, React, TypeScript, Tailwind CSS, Node test runner, Python unittest.

## Global Constraints

- Preserve the import boundary `web/ → api/ → services/ → shared/`.
- Do not mutate or feed projection roles into canonical claims, query planning, Findings, Insights, grounding, drift, calibration, or precedent.
- AI owns `target_relationship`; deterministic code owns only IDs, closed-enum validation, grouping, provenance, and conflict fallback.
- `source_role` may come only from explicit structured provider metadata; absent or conflicting metadata is `unknown`.
- Missing, malformed, or incomplete semantic decisions degrade only the affected projection to `unknown` and never stop Scout.
- Persist both roles in the current final-result envelope; do not add import migrations or legacy branches.
- Keep every record and citation visible; roles affect labels and filtering, never inclusion.
- Preserve existing user edits in Scout stage files.

---

### Task 1: Normalize explicit source-study roles

**Files:**
- Modify: `services/searcher/models.py`
- Modify: `services/searcher/__init__.py`
- Modify: `services/searcher/stages/clinicaltrials.py`
- Create: `tests/test_searcher_clinicaltrials_roles.py`

**Interfaces:**
- Consumes: ClinicalTrials.gov `armGroups[].type`, `armGroups[].interventionNames`, and `interventions[].armGroupLabels` provider fields.
- Produces: `SOURCE_ROLES` and `DevelopmentRecord.source_role: Literal-like str`, defaulting to `unknown`.

- [ ] **Step 1: Write failing adapter tests**

Create controlled ClinicalTrials.gov fixtures proving that experimental, active-comparator, and placebo-control arm metadata survives normalization, that conflicting arm assignments become `unknown`, and that an intervention name without structured arm metadata stays `unknown`.

- [ ] **Step 2: Run the tests and verify the intended failure**

Run: `python -m unittest tests.test_searcher_clinicaltrials_roles -v`

Expected: FAIL because `DevelopmentRecord` does not expose `source_role`.

- [ ] **Step 3: Add the minimal closed contract and provider mapping**

Add:

```python
SOURCE_ROLES = frozenset({
    "experimental", "comparator", "control", "co_intervention", "unknown",
})
```

Validate `DevelopmentRecord.source_role` in `__post_init__`. In the ClinicalTrials adapter, derive roles only from explicit arm-group types. Resolve one explicit role to itself, multiple distinct roles to `unknown`, and no role to `unknown`; never inspect intervention names for semantic hints.

- [ ] **Step 4: Run focused Searcher tests**

Run: `python -m unittest tests.test_searcher_clinicaltrials_roles tests.test_tooluniverse_connector -v`

Expected: PASS.

### Task 2: Make projection identity, grouping, and conflicts explicit

**Files:**
- Modify: `services/searcher/models.py`
- Modify: `services/scout/models.py`
- Modify: `services/scout/projections.py`
- Modify: `services/scout/contract.py`
- Modify: `tests/test_scout_lineage.py`

**Interfaces:**
- Consumes: `DevelopmentRecord.source_role`, `SafetyRecord.source_role`, normalized Findings, and attribute ownership.
- Produces: stable `projection_id`, grouped `source_role`, and default `target_relationship="unknown"` on `DevelopmentProgram` and `SafetySignal`.

- [ ] **Step 1: Extend the existing projection test first**

Add assertions that repeated records preserve provenance, one explicit role survives, conflicting explicit roles collapse to `unknown`, absent roles remain `unknown`, and both projection kinds receive stable `projection_id` values and `target_relationship="unknown"`.

- [ ] **Step 2: Run the focused test and verify failure**

Run: `python -m unittest tests.test_scout_lineage.LineageAndProjectionTests.test_structured_projections_group_records_without_inference -v`

If the actual class name differs, run: `python -m unittest tests.test_scout_lineage -v`

Expected: FAIL on the missing projection fields.

- [ ] **Step 3: Implement grouping without semantic inference**

Use a stable SHA-256 digest of projection kind plus the existing normalized grouping key for IDs. Collect only non-`unknown` source roles while grouping; assign the unique explicit role when exactly one exists and `unknown` otherwise. Add the same fields to safety records and projections for contract symmetry, leaving safety source roles `unknown` unless an adapter explicitly supplies one.

- [ ] **Step 4: Strengthen the final service-boundary contract**

Validate projection ID uniqueness, the two closed role enums, field-reference membership, and supporting-Finding provenance shape in `validate_result_contract`. Do not validate roles against prose or use them to filter a record.

- [ ] **Step 5: Run lineage and contract tests**

Run: `python -m unittest tests.test_scout_lineage -v`

Expected: PASS.

### Task 3: Add one schema-bound projection relationship stage

**Files:**
- Modify: `services/scout/ai_contracts.py`
- Create: `services/scout/stages/projection_classifier.py`
- Modify: `services/scout/pipeline.py`
- Create: `tests/test_scout_projection_classifier.py`

**Interfaces:**
- Consumes: `list[Attribute]`, grouped `DevelopmentProgram` and `SafetySignal` objects, intervention class, and indication.
- Produces: the same projection objects with only `target_relationship` enriched from `direct | analogous | adjacent | unrelated | unknown`.

- [ ] **Step 1: Write failing ID-binding and degradation tests**

Use a small schema-aware fake client to prove that valid ID-bound decisions are applied; unknown IDs, invalid shapes, omitted decisions, and client exceptions leave only the affected projection as `unknown`; and the input Attributes and Findings remain equal before and after classification.

- [ ] **Step 2: Run the new tests and verify failure**

Run: `python -m unittest tests.test_scout_projection_classifier -v`

Expected: FAIL because the classifier and schema contract do not exist.

- [ ] **Step 3: Add the strict batch contract**

Add `projection_relationship_batch(allowed_projection_ids)` with one required array item shape:

```json
{
  "projection_id": "one allowed ID",
  "target_relationship": "direct|analogous|adjacent|unrelated|unknown",
  "reason": "short classification reason"
}
```

The stage validates exact IDs and enum values, rejects duplicate decisions for an ID, and defaults every missing/invalid decision to `unknown`.

- [ ] **Step 4: Implement bounded canonical context and isolated execution**

Render canonical field name, definition, and document target once; render each projection's source-owned name/type plus bounded cited Finding title/excerpt context. Batch items to keep each call bounded. Catch provider errors inside this stage, log one warning, and return the unchanged projections.

- [ ] **Step 5: Wire the stage after grouping only**

In `continue_pipeline`, call the classifier immediately after `build_development_landscape` and `build_safety_signals`. Pass the OpenAI client. Do not pass the classified projections to any other stage or alter progress totals.

- [ ] **Step 6: Verify semantic mapping and core-axis isolation**

Run: `python -m unittest tests.test_scout_projection_classifier tests.test_scout_lineage -v`

Expected: PASS, including an assertion that matches, assessments, conformity, precedents, variables, ledger, and search plan are unchanged when projection decisions vary.

### Task 4: Carry the roles through the API and current final-result contract

**Files:**
- Modify: `api/schemas.py`
- Modify: `web/lib/api.ts`
- Modify: `web/lib/result-file.ts`
- Modify: `web/lib/result-file.test.ts`
- Modify: `services/assistant/legends.py`

**Interfaces:**
- Consumes: serialized Scout projection dataclasses.
- Produces: required projection roles in `ScoutRunResponse`, TypeScript types, final-result version 37, and accurate Assistant definitions.

- [ ] **Step 1: Update the final-result fixture test first**

Add one development and one safety projection carrying stable IDs and both roles. Assert pack/unpack preserves them. Assert a version-36 artifact is rejected rather than migrated.

- [ ] **Step 2: Run the result test and verify failure**

Run: `npm --prefix web run test:result-file`

Expected: FAIL because the TypeScript projection contract lacks the new fields and version 37 is not current.

- [ ] **Step 3: Update API and TypeScript contracts**

Add closed literals for both roles to raw record and projection schemas/types. Make projection ID and roles required in final results. Increment `RESULT_VERSION` from 36 to 37; do not add compatibility code.

- [ ] **Step 4: Correct the Assistant vocabulary**

Describe Landscape as structured development records whose `source_role` and `target_relationship` are separate axes. Describe Safety as direct or contextual signals according to `target_relationship`; remove the inaccurate claim that every safety product is document-stated.

- [ ] **Step 5: Run API and result-boundary tests**

Run: `python -m unittest tests.test_scout_lineage -v`

Run: `npm --prefix web run test:result-file`

Expected: PASS.

### Task 5: Present direct and contextual projections clearly

**Files:**
- Modify: `web/app/scout/page.tsx`
- Create: `web/lib/scout-projection-roles.ts`
- Create: `web/lib/scout-projection-roles.test.ts`
- Modify: `web/package.json`

**Interfaces:**
- Consumes: persisted `source_role` and `target_relationship`; performs no model call or recalculation.
- Produces: consistent labels, relationship filters, and explanatory copy for Landscape and Safety.

- [ ] **Step 1: Write failing presentation-helper tests**

Test literal labels for all closed values, contextual/direct grouping, and filtering that retains `unknown` rather than silently hiding it.

- [ ] **Step 2: Run the helper test and verify failure**

Run: `npm --prefix web run test:projection-roles`

Expected: FAIL because the helper module/script does not exist.

- [ ] **Step 3: Implement the shared presentation vocabulary**

Create pure helpers for relationship labels, source-role labels, contextual status, and filtering. Use sentence-case copy and one neutral label for `unknown`.

- [ ] **Step 4: Update both tabs without changing record inclusion**

Rename Landscape search/empty copy from “program” to “development record.” Add a relationship Select with `All`, `Direct`, `Analogous`, `Adjacent`, `Unrelated`, and `Unknown`. Show the relationship first and source-study role second when known. In Safety, show the same relationship label and explain that analogous/adjacent items are context, not safety findings attributed to the uploaded product. Preserve every details panel and citation.

- [ ] **Step 5: Run presentation, type, and focused web tests**

Run: `npm --prefix web run test:projection-roles`

Run: `npm --prefix web run typecheck`

Expected: PASS.

### Task 6: Verify the cross-layer change

**Files:**
- Review: all files changed by Tasks 1–5

**Interfaces:**
- Consumes: the completed implementation.
- Produces: fresh evidence that contracts, tests, and production assets agree.

- [ ] **Step 1: Run Python compilation and the full Python test suite**

Run: `python -m compileall api services shared tests`

Run: `python -m unittest discover -s tests -v`

- [ ] **Step 2: Run every web contract test**

Run: `npm --prefix web run test:evidence-map`

Run: `npm --prefix web run test:comparator-plot`

Run: `npm --prefix web run test:quantitative-review`

Run: `npm --prefix web run test:scout-review`

Run: `npm --prefix web run test:result-file`

Run: `npm --prefix web run test:projection-roles`

- [ ] **Step 3: Run TypeScript and production-build verification**

Run: `npm --prefix web run typecheck`

Run: `npm --prefix web run build`

- [ ] **Step 4: Check diff hygiene and invariants**

Run: `git diff --check`

Review that no role field is read outside projections, API serialization, Assistant definitions, final-result typing, and UI rendering; that no legacy branch was added; and that the user's staged Scout prompt changes remain intact.
