# Reviewer

Grades a document against a TPP rubric across two independent dimensions:
**completeness** and **adherence**.

> Folder: `services/reviewer/` · User-facing name: **Reviewer**

## Inputs and outputs

| | |
|---|---|
| Input | One document + header `(org, source_type, intervention_class, indication)` |
| Output | `ReviewResult` — document-, section-, and variable-level grades across the two dimensions |

Pipeline: parse + label (chunker) -> grade.

## Two grading dimensions

| Dimension | Question | Inputs |
|---|---|---|
| `completeness` | Are required variables filled with substantive content? | Rubric + draft |
| `adherence` | Does it follow the rubric's structural rules? | Rubric + draft |

Each dimension is graded by its own LLM call with scoped inputs.

## Files

| File | Purpose |
|---|---|
| `models.py` | `ReviewConfig`, `SectionSpec`, `VariableSpec`, `ReviewResult`, `SectionGrade`, `VariableGrade`, `DimensionGrade`. YAML loader. |
| `pipeline.py` | `run_pipeline(file, ...)` and `review_blocks(blocks, ...)`. Section grades roll up to document grades via section weights. |
| `stages/grader.py` | Two parallel dimension calls per section; merges into `SectionGrade.dimensions`. |
| `cli.py` | Headless batch export to CSV. |
| `configs/` | One YAML per `(org, source_type, intervention)`. |

## Configs

Filename: `{org}_{source_type}_{intervention}.yaml`. Each file declares
the rubric: sections with weights, variables, and optional per-dimension
hint blocks (`completeness:`, `adherence:`).

Bundled: `bmgf_tpp_vaccine.yaml`, `bmgf_tpp_drug.yaml`,
`bmgf_tpp_diagnostic.yaml`, `bmgf_tpp_device.yaml`.

## Public contract

From `__init__.py`:

- `run_pipeline`, `run_pipeline_batch`, `review_blocks`, `review_blocks_batch`
- `ReviewResult`, `ReviewConfig`, `BatchReviewResult`
- `find_config`, `review_result_to_dict`
- `DEFAULT_MAX_OUTPUT_TOKENS`

## Dependencies

Imports `chunker` for parse + label. Never imported by chunker.
