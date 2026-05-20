# Reviewer

Grades a document against a TPP rubric across three independent dimensions: **completeness**, **adherence**, **expertise**. The expertise dimension uses peer claims (from Benchmarker's corpus) as comparator.

> Folder: `services/reviewer/` · User-facing name: **Reviewer**

## Inputs and outputs

| | |
|---|---|
| Input | One document + header `(org, source_type, intervention_class, indication)` + (optionally) a `ClaimsStore` for peer comparison |
| Output | `ReviewResult` — document-, section-, and variable-level grades across the three dimensions |

Pipeline: parse + label (chunker) → grade.

## Three grading dimensions

| Dimension | Question | Inputs |
|---|---|---|
| `completeness` | Are required variables filled with substantive content? | Rubric + draft |
| `adherence` | Does it follow the rubric's structural rules? | Rubric + draft |
| `expertise` | Is what's there high-quality and defensible vs. peers? | Rubric + draft + **peer claims** |

Each dimension is graded by its own LLM call with scoped inputs. Peer claims are structurally absent from the completeness and adherence calls — no leakage.

## Files

| File | Purpose |
|---|---|
| `models.py` | `ReviewConfig`, `SectionSpec`, `VariableSpec`, `ReviewResult`, `SectionGrade`, `VariableGrade`, `DimensionGrade`. YAML loader. |
| `pipeline.py` | `run_pipeline(file, ...)` and `review_blocks(blocks, ...)`. Section grades roll up to document grades via section weights. |
| `stages/grader.py` | Three parallel dimension calls per section; merges into `SectionGrade.dimensions`. Routes peer claims per variable via `attribute_ref`, filtered by `indication`. |
| `cli.py` | Headless batch export to CSV. |
| `configs/` | One YAML per `(org, source_type, intervention)`. |

## Configs

Filename: `{org}_{source_type}_{intervention}.yaml`. Each file declares the rubric: sections with weights, variables with `attribute_ref` (routing key to peer claims), and optional per-dimension hint blocks (`completeness:`, `adherence:`, `expertise:`).

Bundled: `bmgf_tpp_vaccine.yaml`, `bmgf_tpp_drug.yaml`, `bmgf_tpp_diagnostic.yaml`, `bmgf_tpp_device.yaml`.

## Public contract

From `__init__.py`:

- `run_pipeline`, `run_pipeline_batch`, `review_blocks`, `review_blocks_batch`
- `ReviewResult`, `ReviewConfig`, `BatchReviewResult`
- `find_config`, `review_result_to_dict`
- `DEFAULT_MAX_OUTPUT_TOKENS`

## Dependencies

Imports `chunker` (parse + label) and `benchmarker` (`FileClaimsStore` for peer claims). Never imported by either.
