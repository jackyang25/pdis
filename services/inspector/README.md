# Inspector

One product-development document against its configured quality rubric.

## Background

Inspector measures document quality, not investment merit. It does not assign
program risk, validate real-world feasibility, recommend funding, or search
external evidence.

Inspector judges one document against an authored rubric. Comparing two documents
against each other is Aligner's responsibility; the two tools have different
comparison targets and neither substitutes for the other.

## Usage

Import pipeline entry points, result and config models, config lookup, and
serializers from `services.inspector`.

## Contract

| Direction | Value |
|---|---|
| Input | One document or `ContentBlock` list, `InspectionConfig`, indication, and an injected model client |
| Output | Every rubric section, every unit beneath it with its verdict, and the conflicts no unit owns |

There is one published atom. An **`Assessment`** is one rubric unit and how it
stands: one `verdict`, one `statement` saying what is wrong, and the exact blocks it
was read from. A unit *is* its assessment — there is nothing nested inside it — so a
unit cannot carry two answers to one question.

Every section holds at least one unit: a section with variables contributes one
unit per variable, and a section without them is itself one unit whose
`variable_name` is `None`. There is no prose-versus-table branch for a consumer to
get wrong.

## One vocabulary

`VERDICTS` is the whole vocabulary, declared worst-first after `specified`, in
`models.py`:

| Verdict | Meaning |
|---|---|
| `specified` | the rubric asks for this and the document supplies it usably |
| `not_present` | nothing is there |
| `placeholder` | a token such as `<<TBD>>` sits where the value belongs |
| `insufficient` | present, but part of what the requirement asks for is absent |
| `vague` | covers the requirement, but is unusable as stated |
| `section_conflict` | two sections state claims that cannot both hold |
| `not_applicable` | the rubric accepts absence here and the document omits it |

`insufficient` and `vague` are not degrees of each other, and the prompt states the
test rather than leaving it to two adjectives: **coverage first, then usability.** Is
any part of what the requirement asks for absent? Then `insufficient`. Only if the
content covers the whole requirement and is still unusable is it `vague`. A unit that
is both is `insufficient`.

**One axis, and there is no second one.** There used to be three over the same fact:
a `reason` the model chose, a `level` that was a lookup on the reason, and a `status`
that bucketed the levels into three. The second carried nothing the first did not,
and the third re-expressed the second in different words — so a reader saw
"Insufficient" on a finding and "Not met" on the unit above it and had no way to know
those were one judgement said twice. The keys collided too: the reason `unmet`
rendered as "Insufficient" while the status `not_met` rendered as "Not met".

There is no `recommendation` either. It restated the statement as an imperative —
"Vial size is not specified" beside "Specify vial size" — and the web layer had grown
a guard to hide one of the two. Where the imperative carried something the statement
did not, which was one case, the fact moved into the statement.

There is no `off_template` either, and it was the last value that did not belong. It
named a deviation in structure or naming, which is a different question from every
other verdict: the rest ask what the content says, that one asked what shape it was
in. A unit that was both misnamed and unmeasurable had to be filed as one of them, and
the other fact was lost. A layout that costs a reader something now shows up as
`insufficient` or `vague` on its own merits; a layout that costs them nothing is not
Inspector's business.

`not_applicable` comes only from the rubric's `optional` flag: whether absence is
acceptable is the author's decision, never the model's, and `Assessment` refuses it on
a required unit rather than trusting the reply. Left ungated, a model could drop a real
shortfall out of the worklist by calling it not applicable.

Conformance language throughout, deliberately not severity language. Inspector
knows what the rubric asked and what the document supplies; it does not know what
a shortfall costs a given programme, so it does not claim one. There is no letter
grade and no overall score.

## How a unit is assessed

**One model call per unit, and one verdict back.** That replaced three calls per
unit — completeness, adherence, and rigor — which cost three times the requests and
could each report the same defect under its own axis. Merging them also removed the
naming split that came with it, where one axis was `adherence` in the data and
"Template adherence" in two interfaces.

The reply is one object, not a list of them. A list let a unit come back with several
answers to one question, so every layer above had to reconcile them into the one
thing a row can show.

`not_present` and `not_applicable` are the only verdicts that cite nothing, and the
only ones exempt from citing. Every other verdict names the block it was read from —
including `specified`, which is a claim about content someone saw. The parser
enforces this so a bad reply gets the retry; `contract.py` enforces it again for an
imported result.

A unit nobody assessed is refused rather than filled in. The assessor makes one call
per unit, so a missing answer is a failed call, and "not checked" reading as "nothing
wrong" is the one mistake this tool cannot make.

Ordering is the verdict's place in the vocabulary above, then the sequence the rubric
author wrote. That is the only
authored priority signal in the system, and it costs nothing: it replaced a
per-section `weight` that nobody calibrated, had one consumer, and sat in eleven
configs.

`assessment_status` and `consistency_status` report whether the run completed. They
are process facts kept outside the assessment, because "not checked" must never
read as "nothing found". A failed unit stops the run, so a partial assessment
cannot become a downloadable result; the cross-section pass is additive and reports
its own failure instead.

## Layout

| Module | Owns |
|---|---|
| `models.py` | shapes and the published vocabulary |
| `assembly.py` | the join of rubric and verdicts, and the ranking |
| `stages/assessor.py` | what the model is asked, and what is accepted back |
| `contract.py` | the deterministic checks, on a fresh or imported result |
| `pipeline.py` | the order those run in |

## Where a rubric comes from

A rubric mirrors an authored source template for its **structure**: the section
list, the unit names, and the column conventions. Each config records which source
in its `mirrors:` field, and that field is published to the in-app docs page beside
the prompts, so "is this the official template" is answerable from the file rather
than from memory.

Everything that makes a rubric *assessable* is authored here and is not in the
source template: each unit's `description`, the `stage_guidance`, the `optional`
flags, and the `expectations`. When the source template changes, the mirrored half
needs re-syncing; the added half is maintained in this repository.

`mirrors:` is a pointer, not a drift check. The source template lives outside the
repository, so nothing here can verify it — which is precisely why the field exists:
it names what to go and check.

## Development

Rubrics live in `configs/{org}_{source_type}_{intervention}.yaml`. A section and a
variable declare the same four things — `name`, `description`, `optional`,
`expectations` — so there is one schema to learn; a section adds only `variables`.
Set `optional: true` where the rubric genuinely does not require a unit.
`expectations` is read into the prompt verbatim and is where an external standard
belongs when one applies, as the expectation a unit is held to rather than as a
second rubric.

`VERDICTS` is declared once in `models.py` and mirrored in `web/lib/api.ts`, bound by
`inspector-vocabulary.test.ts` — which also fails if a second axis grows back.

Inspector consumes Chunker only through `services.chunker` and never searches
external evidence.
