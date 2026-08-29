# Aligner redesign — where it stands and what is left

**Status:** built and available (2026-08-09). Both stages ship, the tool is
`available` in `web/lib/tools.ts`, and the four decisions this document left open
were made as recorded below.

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

## What was decided

### 1. Result shape — one flat list, no `kind`

The two edges share a shape, so findings are one list and `EdgeSpec` gained
nothing. Both edges are answered by the same question — *what does the reference
document require, and what does the other one do with it* — so a `kind` would have
been a field nothing read. A third edge needing different fields is when that
earns a place in the config.

### 2. Approach — the reference document's requirements are the rubric

Not units extracted from both sides and linked. Extraction reads **only** the
reference document, and each requirement is then judged against the other, one
call each. That is what makes the comparison asymmetric by construction rather
than by a labelling convention, and it is the same shape as Inspector walking an
authored rubric and Screener walking a question bank — a fixed list of items, one
judgement each, against a single authority.

Extraction is one call per comparison, because how many requirements a document
states is a fact about the whole document. That is the case the
one-item-per-request rule exempts, and the shape Scout already uses for units.

### 3. Verdict vocabulary — five values

`meets | exceeds | falls_short | not_comparable | not_addressed`.

`exceeds` is kept apart from `meets` because a candidate well past its target may
mean the target is stale, or the candidate is over-specified — both decisions a
PPL would want to make. `not_comparable` was added over a four-value set because
the common real case is a qualitative claim against a numeric bar: "convenient
dosing" against "annual dosing" is neither worse nor silent, and forcing it into
`falls_short` asserts something the text does not say.

`falls_short` and `not_comparable` carry a required `gap`; the other three refuse
one. Same reasoning as Screener's `missing`: the sentence a reader acts on should be
a field the contract enforces, not a convention prose usually follows.

### 4. What shipped

| | |
|---|---|
| Stages | `stages/requirements.py` (one call per comparison), `stages/assessor.py` (one per requirement, `REQUIREMENTS_PER_REQUEST = 1`) |
| Vocabulary | `models.py` — `ALIGNMENT_VERDICTS`, `VERDICTS_REQUIRING_GAP`, `VERDICTS_REQUIRING_CITATION` |
| Identity | `edge_id` on `AlignmentEdge`, `requirement_id` namespaced by it |
| Contract | each side's citations checked against its own document; one verdict per requirement; the gap and citation rules enforced both ways |
| Envelope | `ANALYSIS_VERSIONS.aligner` 2 → 3; a v2 file carries no findings, so it would render as a run that compared nothing |
| Prompts | two `CatalogEntry` declarations, neither with a framing slot — the role and the question travel in the user message, as Screener's questions do |
| UI | `PriorityPanel`, a five-verdict count row, per-comparison groups, a Documents trace placing **both** sides, `AlignerSignalHelp` |
| Chain | `web/lib/aligner-chain.ts` links two comparisons at the passage they share, so a plan delivering a commitment that falls short upstream is visible without reading both lists |
| Tests | `test_aligner.py` (57) and `test_aligner_pipeline.py` (6) |

The trace is the one place Aligner differs from its peers: a finding has lineage on
both sides, so each places two annotations — the requirement in the document that
sets it, the verdict in the document measured. One annotation carrying blocks from
two documents would let a reader open a passage in the reference document and read
"falls short", which is a claim about the other one.

## Open product questions

- **Version drift** (cTPP v1 vs v2) is a real use case, currently refused by
  design. The config could express it; nothing else supports it.
- **Multiple cTPPs under one investment** — a PPL oversees several. Today each is
  a separate run.

## Where things are

| | |
|---|---|
| Service | `services/aligner/` — 10 files, two stages |
| Config | `services/aligner/configs/alignment.yaml` |
| Rules | `AGENTS.md` § Aligner |
| Detail | `services/aligner/README.md` |
| Tests | `tests/test_aligner.py` — 57, and `tests/test_aligner_pipeline.py` — 6 |
| API | `api/routes/aligner.py`, including `GET /api/aligner/edges` |
| UI | `web/app/aligner/page.tsx` |
