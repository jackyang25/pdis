# Aligner

The iTPP, cTPP, and IPDP against each other: whether the candidate and the plan
deliver what was asked for.

## Background

Aligner judges one document against a second document. Judging a document against
an authored rubric is Inspector's responsibility, and judging it against external
evidence is Scout's; the three tools have different comparison targets and none
substitutes for another. That split is the reason Aligner will never gather
evidence or grade quality, whatever analysis it comes to hold.

The previous analysis extracted typed units from each document and linked them as
`aligned`, `modified`, `conflict`, `missing`, or `introduced`. It was removed
because those relations are symmetric — they describe how two documents differ,
never whether the second meets the bar the first sets:

```
iTPP: annual dosing desired
cTPP: dosing every 6 months  -> modified
cTPP: dosing every 2 years   -> modified
```

One label, opposite meanings for the investment.

## What a run does

Resolves comparisons, parses every document, then for each comparison:

1. **Reads the reference document's requirements** — one call, because how many
   requirements a document states is a fact about the whole document. Each
   requirement is atomic and cites the passage that states it.
2. **Judges each requirement against the other document** — one call each, fanned
   out. Nothing is packed: a document that meets four targets would read as
   compliant on the fifth.

### The five verdicts

| Verdict | Means | Carries `gap` |
|---|---|---|
| `meets` | the measured document satisfies the requirement | no |
| `exceeds` | it does better than the requirement asks | no |
| `falls_short` | it addresses the requirement and states less | **yes** |
| `not_comparable` | it addresses the subject in terms that cannot be measured against the requirement | **yes** |
| `not_addressed` | it says nothing on the subject | no |

Closed and asymmetric. `exceeds` is never folded into `meets`, because a candidate
well past its target may mean the target is stale. `not_comparable` exists so
vagueness is not reported as a shortfall — "convenient dosing" against a bar of
"annual dosing" is neither worse nor silent, and calling it either asserts
something the text does not say.

`gap` is one sentence naming what is still to close. It is required on the two
verdicts that have one and refused on the rest, because that sentence is what a
PPL takes back to whoever wrote the document — leaving it to prose would make it
usually present and never guaranteed.

### Two citation lists, and they are not interchangeable

`reference_block_ids` are blocks of the document that sets the bar;
`comparison_block_ids` are blocks of the document being measured. The assessor's
schema offers only the second, so a verdict cannot be justified by citing the
document that set the bar, and the contract checks both against their own
documents. A result that mixed them would read perfectly and be unfalsifiable.

### Where two comparisons meet

The middle document of a three-document run is measured in the first comparison and
authoritative in the second, so a plan can faithfully deliver a commitment that
itself falls short. Every verdict is correct and the second list reads as good news.

The web layer links the two findings at the passage they both cite —
`web/lib/aligner-chain.ts`, an intersection of block ids, derived on read. No model
call, no stored field, and deliberately no `itpp → ipdp` edge, which would re-report
the same gap and attribute it to the wrong document.

The note it renders is a claim about the passage, not about the requirement: a
paragraph can carry several facts, so the shared citation does not prove both
comparisons meant the same clause. It also stays silent when the two comparisons cite
the commitment in different places — under-reporting rather than matching requirement
text, which would be a fuzzy comparison.

There is no compliance score, and totals are not comparable across comparisons:
the denominator is however many requirements that reference document happens to
state.

## Configuration is the whole design

`configs/alignment.yaml` holds two things, and between them they mean no stage
knows how many documents a run has or which types compare:

```yaml
document_roles:      # how each type is described; `default` is required
  itpp: …
  ctpp: …
  ipdp: …
  default: …

edges:               # which ordered pairs compare, and what each asks
  - reference: itpp
    comparison: ctpp
    question: Does the candidate meet the bar the intervention profile sets?
  - reference: ctpp
    comparison: ipdp
    question: Does the plan deliver what the candidate profile commits to?
```

A run makes every declared comparison whose two documents were supplied, so **two
documents resolve one comparison and three resolve two** — and neither number
appears anywhere in code. Adding a document type is an edit to this file; it
reaches neither `run_pipeline`, the API route, the result schema, nor the upload
form.

Three properties worth keeping:

- **Edges are ordered.** `reference` is honoured, `comparison` is measured against
  it. An iTPP-to-cTPP comparison is not a symmetric diff — the iTPP is the bar.
- **Direction is on the edge, not the document.** A cTPP is the comparison against
  the iTPP and the reference for the IPDP, so a side cannot be a property of a
  file.
- **There is deliberately no `itpp`/`ipdp` pair.** A plan is written against the
  candidate, not against the Foundation's abstract goal, so that comparison
  reports differences the cTPP pair already explains.

## Failing loudly

Both refusals happen before any parsing, because a run that silently compares
nothing looks identical to one that found nothing wrong:

| Situation | Result |
|---|---|
| Documents resolve no declared comparison | Refused, naming what Aligner does compare |
| Two documents of the same type | Refused; screening several candidates at once is a different tool |

## Usage

Import `run_pipeline`, `load_config`, `resolve_edges`, `describe_document`,
`describe_edges`, the result models, and `alignment_result_to_dict` from
`services.aligner`.

| Direction | Value |
|---|---|
| Input | Two or more `DocumentInput`s, shared product context, config, and an injected model client |
| Output | Identified documents, the comparisons they resolve, every parsed block, and one finding per requirement |

## Development

Aligner uses Chunker through its public package and keeps document-type
differences in configuration rather than pipeline branches.

The two shipped edges ask structurally different questions — one whether a
candidate clears a bar, the other whether a plan delivers a commitment — and they
share one result shape, which is why `EdgeSpec` has no `kind`. Both are answered by
"what does the reference document require, and what does the other one do with
it", so a `kind` would be a field nothing read. If a third edge ever needs
different fields, that is when the distinction earns a place in the config rather
than a branch in a stage.
