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
| Output | Variable, section, and document grades plus cited cross-section conflicts |

Completeness, adherence, and rigor are independent judgments. Grades are `A`
through `F` or `N/A`. The configured rubric owns the variable ledger; model
omissions cannot shrink its denominator. Deterministic code calculates rollups,
and a separate consistency pass reports only cross-section conflicts.

Completeness is authoritative for presence. Substantive, partial, or placeholder
content must cite an exact mapped section block; missing or non-applicable
content does not invent lineage. Adherence and rigor are merged only after that
presence decision is established.

Section labels and dimension decisions use schema-bound model outputs. Large
rubric sections are graded in bounded variable batches that retain the complete
mapped section context. Deterministic validation checks rubric coverage and
block lineage; it does not reinterpret prose. A failed core grading batch stops
the run, so incomplete model output cannot become a downloadable final report.

## Development

Rubrics live in `configs/{org}_{source_type}_{intervention}.yaml`. Inspector
consumes Chunker only through `services.chunker` and never searches external
evidence.
