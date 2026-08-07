# Aligner

The iTPP, cTPP, and IPDP against each other: whether the candidate and the plan
deliver what was asked for.
**Between designs — the analysis has been removed.**

## Background

Aligner judges one document against a second document. Judging a document against
an authored rubric is Inspector's responsibility, and judging it against external
evidence is Scout's; the three tools have different comparison targets and none
substitutes for another. That split is the reason Aligner will never gather
evidence or grade quality, whatever analysis it comes to hold.

The previous analysis extracted typed units from each document and linked them as
`aligned`, `modified`, `conflict`, `missing`, or `introduced`. It was removed
because those relations are symmetric — they describe how two documents differ,
never whether the second meets the bar the first sets — and a symmetric answer is
the wrong shape for the comparison users actually make.

## What a run does

Resolves comparisons, parses every document, returns both. It reports no
findings.

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
| Output | Identified documents, the comparisons they resolve, and every parsed block |

## Development

Aligner uses Chunker through its public package and keeps document-type
differences in configuration rather than pipeline branches.

One thing to settle before the next design commits to it: the two shipped edges
ask structurally different questions — one whether a candidate clears a bar, the
other whether a plan delivers a commitment. Nothing in code distinguishes them
today. If they turn out to need different result fields, that distinction becomes
a field on `EdgeSpec` rather than a branch in a stage.
