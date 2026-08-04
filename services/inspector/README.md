# Inspector

Evaluate a product-development document against its configured quality rubric.

## Background

Inspector measures document quality, not investment merit. It does not assign
program risk, validate real-world feasibility, recommend funding, or search
external evidence.

Inspector judges one document against an authored rubric. Comparing two
documents against each other is Aligner's responsibility; the two tools have
different comparison targets and neither substitutes for the other.

## Usage

Import pipeline entry points, result and config models, config lookup, and
serializers from `services.inspector`.

## Contract

| Direction | Value |
|---|---|
| Input | One document or `ContentBlock` list, `InspectionConfig`, indication, and an injected model client |
| Output | Per-variable dimension verdicts, section and document gap counts, plus cited cross-section conflicts |

Completeness, adherence, and rigor are independent judgments. Each returns one
verdict: `critical`, `for_consideration`, `meets`, or `not_applicable`. There is
no letter grade and no overall score, because a letter implied an even scale and
that a section's quality was the mean of its variables. A section and the
document publish gap counts instead, derived from the verdicts beneath them.

The configured rubric owns the variable ledger; model omissions cannot shrink its
denominator. A separate consistency pass reports only cross-section conflicts.

Completeness is authoritative for presence. Substantive, partial, or placeholder
content must cite an exact mapped section block; missing or non-applicable
content does not invent lineage. Adherence and rigor are merged only after that
presence decision is established.

Section labels and dimension decisions use schema-bound model outputs. Large
rubric sections are assessed in bounded variable batches that retain the complete
mapped section context. Deterministic validation checks rubric coverage and
block lineage; it does not reinterpret prose. A failed core batch stops the run,
so incomplete model output cannot become a downloadable final report.

An authored section weight ranks the issue list. It is the one place the rubric
author's sense of what matters most still applies, now that nothing is averaged.

## Development

Rubrics live in `configs/{org}_{source_type}_{intervention}.yaml`. Inspector
consumes Chunker only through `services.chunker` and never searches external
evidence.
