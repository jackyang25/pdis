# Reviewer

Grades a parsed product-development document against its configured rubric on
three independent dimensions: completeness, adherence, and rigor.

## Inputs and outputs

| | |
|---|---|
| Input | One document or pre-parsed `ContentBlock[]`, a `ReviewConfig`, indication, and injected LLM client |
| Output | `ReviewResult` with variable-, section-, and document-level grades plus cross-section conflicts |

Grades are always `A`, `B`, `C`, `D`, `F`, or `N/A`.

## Three grading dimensions

| Dimension | Question |
|---|---|
| `completeness` | Is every required element present and substantive? |
| `adherence` | Does the document follow the rubric's structural and formatting expectations? |
| `rigor` | Is the content specific, measurable, meaningful, and technically sound? |

Each dimension is produced by its own responsibility-scoped LLM call. A call
receives only that dimension's rubric guidance and the relevant document
blocks. The three outputs are merged into a common `dimensions` shape.

## Pipeline

```text
Chunker parse + section mapping
→ grade rubric sections in parallel
  → grade completeness, adherence, and rigor independently
→ deterministic variable → section rollups
→ deterministic section → document rollups
→ one whole-document consistency pass for cross-section conflicts only
```

Variable-bearing sections are graded at the variable level. Prose-only sections
are graded directly. Missing sections and variables receive deterministic
handling. No extra model call synthesizes section or document grades.

Embedded visuals are supplied with their exact block IDs to each applicable
dimension call. Returned block IDs are validated against the section input.

## Files

| File | Purpose |
|---|---|
| `models.py` | Rubric, grade, result, and YAML contracts. |
| `pipeline.py` | Parse/grade orchestration, deterministic rollups, and batch entry points. |
| `stages/grader.py` | Independent dimension calls and cross-section consistency pass. |
| `configs/` | One rubric per `(org, source_type, intervention_class)`. |
| `cli.py` | Headless batch export. |

## Configuration

Filename: `{org}_{source_type}_{intervention}.yaml`. Each rubric declares
sections, weights, optional variables, document-stage grading guidance, and
optional responsibility-specific blocks:

```yaml
completeness: {}
adherence: {}
rigor: {}
```

Bundled BMGF configs cover `itpp` and `ctpp` for vaccine, drug, diagnostic, and
device, plus `ipdp` for vaccine, drug, and diagnostic.

## Public contract

Consumers import only from `services.reviewer`:

- `run_pipeline`, `run_pipeline_batch`
- `review_blocks`, `review_blocks_batch`
- `ReviewResult`, `ReviewConfig`, `BatchReviewResult`
- `find_config`, `review_result_to_dict`
- `DEFAULT_MAX_OUTPUT_TOKENS`

## Dependency boundary

Reviewer depends on Chunker only through `services.chunker`. It does not search
external evidence and is never imported by Chunker.
