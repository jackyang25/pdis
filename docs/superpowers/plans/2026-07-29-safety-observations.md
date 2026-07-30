# Safety Observations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task by task. This checkout contains intentional uncommitted work; preserve it and execute in place.

**Goal:** Replace Scout's ambiguous safety-signal contract with source-faithful safety observations and present FDA labeling, recalls, FAERS, and MAUDE records without implying incidence, causality, severity, or statistical signal strength.

**Architecture:** Preserve the existing `FDA source -> Searcher -> Scout projection -> API/result envelope -> UI` boundary. Searcher owns source normalization, Scout owns deterministic grouping plus the existing display-only product relationship, the API and portable result carry the current contract unchanged, and the UI only groups and explains persisted observations. Remove the superseded `SafetyRecord` / `SafetySignal` path completely; do not add import compatibility.

**Tech Stack:** Python 3 dataclasses, Pydantic/FastAPI, Next.js 14, React, TypeScript, Tailwind CSS, Python `unittest`, Node's built-in test runner.

## Global constraints

- Preserve `web/ -> api/ -> services/ -> shared/` imports.
- Keep source URLs, retrieval paths, field references, and supporting Findings authoritative.
- Do not calculate incidence, shares, disproportionality, EBGM, chi-square, severity, causality, or risk labels from top-event counts.
- Use `report_count` only for source-supplied FAERS counts; never manufacture or sum counts.
- Keep projection relationship display-only and outside grounding, drift, calibration, and precedent.
- Update the current final-result contract directly; reject older shapes rather than migrating them.
- Preserve all unrelated worktree edits.

---

### Task 1: Define the Searcher safety-observation contract

**Files:**
- Modify: `tests/test_tooluniverse_connector.py`
- Modify: `services/searcher/models.py`
- Modify: `services/searcher/__init__.py`
- Modify: `services/searcher/sources/fda_safety.py`

**Contract:**
- Rename `SAFETY_SIGNAL_TYPES` to `SAFETY_RECORD_TYPES`.
- Rename `SafetyRecord` to `SafetyObservationRecord`.
- Rename `Finding.safety_records` to `Finding.safety_observations`.
- Replace `signal_type`, `signal`, and `count` with `record_type`, `source_system`, `label`, and `report_count`.
- `source_system` is one of `fda_label | faers | maude | fda_recall`.
- FAERS records require a non-negative `report_count`; other record types must not invent one.

- [x] **Step 1: Write failing model and adapter assertions**

Extend `tests/test_tooluniverse_connector.py` to assert the four source operations emit the exact record type and source system, only FAERS emits `report_count`, and the existing source-native FAERS URL remains unquoted. Add direct construction tests proving unknown enums, negative counts, missing FAERS counts, and non-FAERS counts are rejected.

- [x] **Step 2: Verify the tests fail for the missing contract**

Run:

```sh
.venv/bin/python -m unittest tests.test_tooluniverse_connector -v
```

Expected: FAIL because `SafetyObservationRecord`, `source_system`, and `Finding.safety_observations` do not exist.

- [x] **Step 3: Implement the minimal normalized contract**

Add the two closed enums and structural validation in `services/searcher/models.py`. Rename Finding storage and merge/deduplication in the same module. Update public exports. Update each FDA adapter operation to emit one source-owned observation with the correct `record_type`, `source_system`, `label`, `detail`, `report_count`, and qualification. Do not add semantic inference.

- [x] **Step 4: Verify Searcher behavior**

Run the focused test again and require PASS.

---

### Task 2: Rename and strengthen the Scout projection

**Files:**
- Modify: `tests/test_scout_lineage.py`
- Modify: `tests/test_scout_projection_classifier.py`
- Modify: `services/scout/models.py`
- Modify: `services/scout/projections.py`
- Modify: `services/scout/stages/projection_classifier.py`
- Modify: `services/scout/pipeline.py`
- Modify: `services/scout/contract.py`
- Modify: `services/scout/__init__.py`

**Contract:**
- Rename `SafetySignal` to `SafetyObservation`.
- Rename `ScoutResult.safety_signals` to `safety_observations`.
- Rename `build_safety_signals` and `safety_signals_to_dicts` accordingly.
- Group by normalized product, record type, source system, and label.
- Retain all attribute references and supporting Findings.
- Repeated identical-scope FAERS retrievals retain the maximum source-supplied count rather than summing it.

- [x] **Step 1: Write failing projection assertions**

Update lineage tests to construct source observations and assert grouping includes `source_system`, distinguishes otherwise identical labels from different systems, deduplicates Finding provenance, preserves field references, retains the maximum repeated FAERS count, and yields stable `projection_id` values. Update classifier tests to use `SafetyObservation` and `projection_kind="safety_observation"`.

- [x] **Step 2: Verify focused tests fail**

Run:

```sh
.venv/bin/python -m unittest tests.test_scout_lineage tests.test_scout_projection_classifier -v
```

Expected: FAIL on the renamed model and result contract.

- [x] **Step 3: Implement the projection rename and grouping**

Update Scout dataclasses, serializers, pipeline wiring, contract validation labels, public exports, and the display-only relationship classifier. Do not pass observations into any evidence axis or change progress semantics.

- [x] **Step 4: Verify projection and lineage behavior**

Run the focused tests again and require PASS.

---

### Task 3: Carry the current contract through API and portable results

**Files:**
- Modify: `api/schemas.py`
- Modify: `api/routes/scout.py`
- Modify: `web/lib/api.ts`
- Modify: `web/lib/result-file.ts`
- Modify: `web/lib/result-file.test.ts`
- Modify: `web/lib/scout-evidence-map.test.ts`
- Modify: `services/assistant/legends.py`

**Contract:**
- Rename raw and projected safety types in Pydantic and TypeScript.
- Rename `safety_records` to `safety_observations` on Findings.
- Rename `safety_signals` to `safety_observations` on Scout results.
- Require `record_type`, `source_system`, `label`, and `report_count` in current final results.
- Increment `RESULT_VERSION` once and add no migration branch.

- [x] **Step 1: Write failing result-envelope assertions**

Update the result fixture to contain one FAERS observation and assert pack/unpack preserves `record_type`, `source_system`, `label`, `report_count`, qualification, relationship, and supporting provenance. Assert the previous result version is rejected.

- [x] **Step 2: Verify the result test fails**

Run:

```sh
npm --prefix web run test:result-file
```

Expected: FAIL because the TypeScript result shape still uses `safety_signals`.

- [x] **Step 3: Update API, TypeScript, import validation, and Assistant vocabulary**

Rename the schemas and serialized fields at the current boundary. Describe safety observations as official information or surveillance records, with FAERS counts explicitly non-incidence and non-causal. Do not duplicate Finding URL/query/retrieval metadata into an observation.

- [x] **Step 4: Verify API and result boundaries**

Run:

```sh
.venv/bin/python -m unittest tests.test_scout_lineage -v
npm --prefix web run test:result-file
npm --prefix web run test:evidence-map
```

Expected: PASS.

---

### Task 4: Add a pure safety presentation model and two-section UI

**Files:**
- Create: `web/lib/scout-safety-observations.ts`
- Create: `web/lib/scout-safety-observations.test.ts`
- Modify: `web/package.json`
- Modify: `web/app/scout/page.tsx`

**Presentation:**
- `Official safety information`: `label_warning` and `recall`.
- `Reported-event surveillance`: `reported_event` and `device_event`.
- Show source system, product, label, persisted relationship, and FAERS count only.
- Expanded content shows detail, qualification, relationship reason, and cited Findings.
- Omit empty sections; show one empty state when neither section has observations.

- [x] **Step 1: Write failing pure-helper tests**

Test section grouping, section order, source-system labels, FAERS-only count wording, relationship filtering without record loss, and omission of empty sections.

- [x] **Step 2: Verify the helper test fails**

Add `test:safety-observations` to `web/package.json`, then run:

```sh
npm --prefix web run test:safety-observations
```

Expected: FAIL because the helper module does not exist.

- [x] **Step 3: Implement the pure presentation helpers**

Create functions that group and label persisted data without recalculation. Keep copy in sentence case and keep unknown values visible.

- [x] **Step 4: Rebuild the Safety tab on the helper**

Replace the single undifferentiated list with the two groups. Keep the existing search and relationship filter. Put the relevant qualification next to each group and retain expandable record details and citations. Remove “signal” language from user-facing copy.

- [x] **Step 5: Verify UI helpers and types**

Run:

```sh
npm --prefix web run test:safety-observations
npm --prefix web run test:projection-roles
npm --prefix web run typecheck
```

Expected: PASS.

---

### Task 5: Verify the complete cross-layer change

**Files:**
- Review all files changed by Tasks 1-4.

- [x] **Step 1: Prove the old contract is gone**

Run:

```sh
rg -n "SafetyRecord|SafetySignal|SAFETY_SIGNAL_TYPES|safety_records|safety_signals|build_safety_signals|safety_signals_to_dicts" api services tests web --glob '!**/node_modules/**'
```

Expected: no matches.

- [x] **Step 2: Run Python compilation and tests**

Run:

```sh
PYTHONPYCACHEPREFIX=/tmp/pdis-pycache .venv/bin/python -m compileall -q shared services api tests
.venv/bin/python -m unittest discover -s tests -v
```

- [x] **Step 3: Run all web contract tests**

Run every `test:*` script in `web/package.json`, including the new safety-observation test.

- [x] **Step 4: Run production verification**

Run:

```sh
npm --prefix web run typecheck
npm --prefix web run build
git diff --check
```

- [x] **Step 5: Audit scope and provenance**

Confirm that the only consumers of safety observations are Searcher normalization, Scout projection/classification, API serialization, final-result typing, Assistant definitions, and UI rendering; counts are never summed or converted into risk statistics; source failures remain isolated; and no compatibility or legacy path was introduced.
