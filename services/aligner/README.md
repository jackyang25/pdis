# Aligner

The iTPP, cTPP, and IPDP against each other: whether the candidate and the plan
deliver what was asked for.

## Background

Aligner judges one document against a second document. Judging a document against
an authored rubric is Inspector's responsibility, and judging it against external
evidence is Scout's; the three tools have different comparison targets and none
substitutes for another. That split is the reason Aligner will never gather
evidence or grade quality, whatever analysis it comes to hold.

## Scope

**Aligner determines whether the documented plan supports the documented objectives,
not whether those objectives are achievable.**

The test is mechanical: **both sides must be readable off the page.** If answering a
question needs anything that is not written in the two documents, it is not Aligner's.

| Question | Aligner? |
|---|---|
| Does the cTPP commit to <$3/dose? | yes — read it |
| Does the IPDP carry cost-reduction work? | yes — read it |
| Is <$3 achievable for this platform? | no — needs the world, so Scout's |
| Is that work *enough* to reach <$3? | no — needs a person who knows the field |

**"Enough" is the trip-wire.** The moment a verdict means *sufficient* rather than
*present*, the tool has left its authority and is asserting something neither document
says. The assessor prompt states this as a rule, because it is the one boundary a model
crosses without noticing.

Coverage across the three tools, by the authority each judges against:

```
a rubric            ->  Inspector   is this document usable?
another document    ->  Aligner     do the documents agree?
external evidence   ->  Scout       do the claims hold up?
```

Deliberately owned by none of them: *will this plan work.* Scout judges a target against
the world, not a plan against the world. A skill can put Scout's precedent beside
Aligner's workstream in front of a reader; the judgement stays with the reader.

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

### What honouring a requirement means

It depends on the kind of document, and the config's `document_roles` line is what says
which kind this is:

- A **profile** — an iTPP or cTPP — honours a requirement by **stating a value** that
  satisfies it. Committing to numbers is its job.
- A **plan** — an IPDP — honours a commitment by **carrying the work** directed at it:
  a study, an activity, a milestone, a decision point. Saying how is its job, and
  restating the number is not.

This was wrong for one of the two edges and the wording is why. The verdicts read "this
document states something that satisfies the requirement", which a plan fails by
construction: an IPDP scheduling a 24-month stability study states no temperature, so a
commitment it had a whole study for came back as `not_addressed`. A reader saw "the plan
does not address stability."

Nothing was added to fix it — no sixth verdict, no second axis, no third comparison. The
document's role already reached the prompt; it was simply not allowed to change what the
verdicts meant.

### The five verdicts

| Verdict | Means |
|---|---|
| `meets` | the measured document satisfies the requirement |
| `exceeds` | it does better than the requirement asks |
| `falls_short` | it addresses the requirement and states less |
| `not_comparable` | it addresses the subject in terms that cannot be measured against the requirement |
| `not_addressed` | it says nothing on the subject |

Closed and asymmetric. `exceeds` is never folded into `meets`, because a candidate
well past its target may mean the target is stale. `not_comparable` exists so
vagueness is not reported as a shortfall — "convenient dosing" against a bar of
"annual dosing" is neither worse nor silent, and calling it either asserts
something the text does not say.

A finding carries **one** sentence: `statement`, what the measured document says on
the subject. There was a second, `gap`, asked to name the distance from the bar on the
two verdicts that have one — and the distance turned out not to be a third fact. It is
the requirement and the statement, which the reader already has: the requirement heads
the row and the statement sits under it. What came back said so plainly:

```
requirement  The target population minimum target is pregnant women 24-36 weeks.
statement    The candidate sets the minimum as pregnant women at least 28 weeks.
gap          Pregnant women 24-36 weeks required versus at least 28 weeks offered.
```

The prompt told it not to restate the requirement; it restated the requirement, on
every one of sixty-nine rows, because on a shortfall there is nothing else to say.

### Two citation lists, and they are not interchangeable

`reference_spans` quote the document that sets the bar; `comparison_spans` quote
the document being measured. The assessor's schema offers only the second, so a
verdict cannot be justified by citing the document that set the bar, and the
contract checks both against their own documents. A result that mixed them would
read perfectly and be unfalsifiable.

A span carries the exact lines, not just the block they sit in, and the model never
types them: it selects a `block_id` and a `start_line`/`end_line` range out of the
line-labelled view in `context.py`, and `shared.spans` copies those lines from the
block. That is why the trace underlines a sentence rather than shading a whole table,
and why the contract can check a quote against its own block — a quotation appearing
in no document is not something the pipeline can produce.

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
