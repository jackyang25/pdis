# Inspector

Evaluate a product-development document against its configured quality rubric.

## Background

Inspector measures document quality, not investment merit. It does not assign
program risk, validate real-world feasibility, recommend funding, or search
external evidence.

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

## Development

Rubrics live in `configs/{org}_{source_type}_{intervention}.yaml`. Inspector
consumes Chunker only through `services.chunker` and never searches external
evidence.
