# Inspector

Evaluate a product-development document against its configured quality rubric.

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
| Output | Every rubric section, every unit beneath it with its status and findings, and the conflicts no unit owns |

There is one published atom. A **`Finding`** is one thing to fix: one statement,
one recommendation, one `reason`, and the exact blocks it was read from. A
**`UnitAssessment`** is one rubric unit and owns the findings raised against it,
so a finding cannot belong to two units or to none.

Every section holds at least one unit: a section with variables contributes one
unit per variable, and a section without them is itself one unit whose
`variable_name` is `None`. There is no prose-versus-table branch for a consumer to
get wrong.

## One vocabulary

`FINDING_REASONS` is the whole vocabulary, declared worst-first in `models.py`:

| Reason | Meaning | Level |
|---|---|---|
| `missing` | nothing is there | `not_met` |
| `placeholder` | a token such as `<<TBD>>` sits where the value belongs | `not_met` |
| `unmet` | present, and does not satisfy the requirement | `not_met` |
| `off_template` | structure or naming deviates from the rubric | `could_be_stronger` |
| `unclear` | satisfies the requirement but is vague | `could_be_stronger` |
| `conflicting` | two sections state claims that cannot both hold | `not_met` |

`level` is derived from `reason`, and a unit's `status` is derived from the levels
on that unit, so `met` means exactly zero findings and no consumer can arrive at a
different answer. `not_applicable` comes only from the rubric's `optional` flag:
whether absence is acceptable is the author's decision, never the model's.

Conformance language throughout, deliberately not severity language. Inspector
knows what the rubric asked and what the document supplies; it does not know what
a shortfall costs a given programme, so it does not claim one. There is no letter
grade and no overall score.

## How a unit is assessed

**One model call per unit**, asking what is wrong and why. That replaced three
calls per unit — completeness, adherence, and rigor — which cost three times the
requests and could each report the same defect under its own axis. Merging them
also removed the naming split that came with it, where one axis was `adherence` in
the data and "Template adherence" in two interfaces.

A unit raises each reason at most once, and `missing` silences the rest: absence is
not also off-template or unclear, and there is nothing there to have read.

`missing` is the only reason that cites nothing, and the only one exempt from
citing. Every other finding names the block it was read from, so a reader can check
it against the document. The parser enforces this so a bad reply gets the retry;
`contract.py` enforces it again for an imported result.

Ordering is `level`, then the sequence the rubric author wrote. That is the only
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
| `assembly.py` | the join of rubric and findings, and the ranking |
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

`FINDING_REASONS`, `FINDING_LEVELS`, and `UNIT_STATUSES` are declared once in
`models.py` and mirrored in `web/lib/api.ts`, bound by
`inspector-vocabulary.test.ts`.

Inspector consumes Chunker only through `services.chunker` and never searches
external evidence.
