# Aligner redesign — where it stands and what is left

**Status:** input layer built and shipped. Analysis not started. The tool is
marked `coming_soon` in `web/lib/tools.ts`; the route and page still work for
development.

This document exists so the next person to open Aligner does not have to
reconstruct the reasoning from git history.

## Why the old analysis was removed

Aligner extracted typed units from two documents and labelled each pair
`aligned | modified | conflict | missing | introduced`.

Those relations are **symmetric** — they describe how two documents differ, never
whether the second meets the bar the first sets. Concretely:

> iTPP: annual dosing desired
> cTPP: dosing every 6 months → `modified`
> cTPP: dosing every 2 years → `modified`

Same label, opposite meaning for the investment. An iTPP-to-cTPP comparison is
not a diff: the iTPP is the standard the candidate is screened against.

The old code also had a live bug — `validate_result_contract` had no `return`, so
`run_pipeline` returned `None`. It was untested because the tests called the
validator directly and only asserted it did not raise.

## Who this is for

The user is the **PPL** (Product & Portfolio Lead), who oversees one or more
investments. Each investment has an iTPP (Foundation-authored, states what is
wanted), a cTPP (grantee-authored, describes the candidate being developed in
response), and an IPDP (grantee-authored, the plan). The PPL ensures an iTPP is
in place and provides product-development leadership.

The reported workflow: compare a cTPP and iTPP for drift, resolve it, and
separately gather evidence to support unified changes.

## What was built

`configs/alignment.yaml` declares the documents and the comparisons:

```yaml
document_roles:      # how each type is described; `default` required
edges:               # ordered pairs, each with the question it asks
  - reference: itpp
    comparison: ctpp
    question: Does the candidate meet the bar the intervention profile sets?
  - reference: ctpp
    comparison: ipdp
    question: Does the plan deliver what the candidate profile commits to?
```

No stage knows how many documents a run holds or which types compare. Two
documents resolve one comparison, three resolve two. Adding a document type is a
config edit and must not reach `run_pipeline`, the route, the schema, or the
upload form.

Direction lives on the edge, not the document: a cTPP is the comparison against
the iTPP and the reference for the IPDP.

## Decisions already made — do not relitigate without reason

| Decision | Why |
|---|---|
| No `itpp` → `ipdp` edge | A plan is written against the candidate, not the Foundation's abstract goal. That edge reports differences the cTPP pair already explains. |
| No evidence in Aligner | Each tool judges against one authority. The evidence questions a gap raises ("is annual dosing achievable?") are per-document — Scout's job, run separately. Aligner must not reference Scout output; a field justified by another tool's result belongs to that tool. |
| No same-type pairs | Two revisions of one document is a different question. The config refuses it. |
| No one-to-many screening | cTPPs are tied to investments; this is not a candidate-filtering tool. |
| Context documents stay out | PDSS, Business Case, Value Proposition, Stage Gate Notes, Meeting Notes make no commitments, so there is nothing to hold another document to. A PPL who needs them while reviewing drift uses Ask. |
| Acceptance is not recorded | PDIS is stateless. When a PPL accepts a deviation they edit the document, and the next run agrees. The documents are the state. |

## What is left

### 1. Decide the result shape — blocks everything else

The two shipped edges ask structurally different questions:

- **screening** (iTPP → cTPP): does the candidate clear the bar?
- **derivation** (cTPP → IPDP): does the plan deliver the commitment?

If they need different fields, findings are per-edge and `EdgeSpec` gains a
`kind`. If they share a shape, findings are one flat list and no `kind` is
needed. `kind` was deliberately left out rather than added speculatively.

If the two turn out to share no result shape at all, that is the signal these are
two tools wearing one name.

### 2. Choose the verdict vocabulary

Closed, asymmetric, direction-aware — something in the shape of *meets / falls
short / exceeds*, replacing `modified`. This is the whole reason the old
vocabulary went; getting it wrong reproduces the original defect.

### 3. Decide whether units still exist

The old design extracted units per document, then linked them. That was
inherited, not re-decided. The alternative is comparing directly, item by item,
the way Inspector walks a rubric. Worth an explicit choice.

### 4. Build the stage

One call per item (throughput from fan-out, never packing). Closed enum. Block
lineage on both sides. A `CatalogEntry` in `prompt_catalog.py` — currently an
empty tuple, and `tests/test_prompt_reference.py` expects Aligner absent from the
published tools, so that expectation moves when the first prompt lands.

### 5. Surface it

Findings on `AlignmentResult`, contract checks beside the structural ones,
`ANALYSIS_VERSIONS.aligner` 2 → 3, the shared `PriorityPanel` for what to look at
first, and another pass on `ALIGNER_LEGEND`, the docs graph in
`product_knowledge.json`, and both READMEs.

Flip `availability` back to `available` in `web/lib/tools.ts`.

## Open product questions

- **Version drift** (cTPP v1 vs v2) is a real use case, currently refused by
  design. The config could express it; nothing else supports it.
- **Multiple cTPPs under one investment** — a PPL oversees several. Today each is
  a separate run.

## Where things are

| | |
|---|---|
| Service | `services/aligner/` — 8 files, no stages |
| Config | `services/aligner/configs/alignment.yaml` |
| Rules | `AGENTS.md` § Aligner |
| Detail | `services/aligner/README.md` |
| Tests | `tests/test_aligner.py` — 29, covering config, edge resolution, contract |
| API | `api/routes/aligner.py`, including `GET /api/aligner/edges` |
| UI | `web/app/aligner/page.tsx` |
