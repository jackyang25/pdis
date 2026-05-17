# PD Reviewer

PD Reviewer reviews PD document completeness and adherence against a document-type rubric, then produces a graded report card. The bundled TPP configs currently cover vaccine, drug, diagnostic, and medical device TPPs.

It uses the chunker as a library for document parsing and section labeling, then runs review prompts over the labeled content.

## Files

| File | Purpose |
|---|---|
| `models.py` | Shared dataclasses: `ReviewConfig`, `ReviewResult`, `SectionGrade`, `VariableGrade`; YAML config loader. |
| `stages/grader.py` | Prompt builder, provider-neutral LLM calls, JSON validation, and section grading. |
| `pipeline.py` | Stateless orchestrator: chunker.pipeline.run_pipeline → grade_sections → ReviewResult. Library entry point. |
| `cli.py` | Headless CLI that grades a chunker package into `document_scores.csv`, `section_grades.csv`, `variable_grades.csv`, `summary.csv`, and `manifest.json`. |
| `configs/` | Review rubrics for supported TPP families: vaccine, drug, diagnostic, and medical device. |
| `requirements.txt` | Library runtime dependencies (no Streamlit). |

The Streamlit UI for this library lives in `dashboard/pd_reviewer_tool.py`.
LLM provider abstraction is shared at the repo root: `llm_client.py`.

PD Reviewer imports chunker APIs for parsing and section labeling:

- `chunker.pipeline.run_pipeline` (orchestrates parse + map in one call)
- `chunker.models.load_config`

PD Reviewer provides its own LLM client and injects it into chunker.pipeline. This keeps it independently distributable while still reusing chunker logic.

## Setup

From the repository root:

```bash
source .venv/bin/activate
python -m pip install -r chunker/requirements.txt
python -m pip install -r pd_reviewer/requirements.txt
```

Set an API key in the environment or enter it in the Streamlit sidebar:

```bash
export ANTHROPIC_API_KEY="your-key"
# or
export OPENAI_API_KEY="your-key"
```

## Run

Use the unified root app:

```bash
streamlit run dashboard/app.py
```

Or run PD Reviewer directly:

```bash
streamlit run dashboard/pd_reviewer_tool.py
```

## ReviewConfig

Review behavior is driven by YAML, not hardcoded logic. Bundled configs include:

```text
services/pd_reviewer/configs/gates_tpp_vaccine.yaml
services/pd_reviewer/configs/gates_tpp_drug.yaml
services/pd_reviewer/configs/gates_tpp_diagnostic.yaml
services/pd_reviewer/configs/gates_tpp_device.yaml
```

The config defines:

- `type_key`: Stable document-type key.
- `display_name`: UI label.
- `org` / `source_type` / `intervention_class`: Header — used to resolve the matching chunker config automatically.
- `sections`: Ordered section rubric with section names, descriptions, weights, and expected variables.

Section names must match the chunker's `section_label` taxonomy.

## How Grading Works

The grading flow has three layers:

1. Chunker parses the uploaded document into blocks and labels each block with a section using the selected LLM client.
2. PD Reviewer grades each configured section with the selected LLM.
3. The overall grade is computed from section grades using the weights in the config.

For sections with expected variables, such as a TPP executive summary table, the grader asks the LLM to:

- determine which expected variables are present
- list missing variables
- grade each present variable
- return source `block_ids` for each variable grade
- assign a section grade based on completeness and adherence

For prose sections with no expected variables, the grader returns only a section-level grade, issues, and recommendation.

The section grade is returned by the LLM. It is not computed as a simple average of variable grades, because the section may include broader context, prose, notes, or structural issues. The overall document grade is deterministic: section grades are converted to numeric scores and weighted by each section's configured `weight`.

## ReviewResult Schema

A single-document review returns a `ReviewResult` dataclass with:

- `doc_id`
- `overall_grade`
- `top_issues`
- `section_grades`

Each `SectionGrade` includes:

- section-level grade and `is_present` flag
- `missing_variables`
- `issues`
- `recommendation`
- `variable_grades`: per-variable grades with source `block_ids`

The Streamlit UI includes a download button for the full JSON report. Batch runs produce CSV tables instead — see *Export A Review Package* below.

## Export A Review Package

For batch review, use `cli.py` to grade an entire chunker package and write a review package on disk. The review package is a flat folder of CSVs plus a manifest, mirroring the chunker's export shape.

### Input

A parsed + mapped chunker package directory containing at minimum:

```text
documents.csv
content_blocks.csv
```

Reviewer reads these read-only; the chunker package is never modified.

### Run

```bash
source .venv/bin/activate
export OPENAI_API_KEY="..."

python -m services.pd_reviewer.cli <chunker_package_dir> <review_package_dir> \
  --max-workers 8 --max-tokens 32000
```

The header (`org`, `source_type`, `intervention_class`) is read from the chunker package's `documents.csv` — no need to pass it again. The rubric config is resolved by `{org}_{source_type}_{intervention}.yaml`.

CLI options:

- `--therapeutic-area` (optional) stamps a disease tag on every output row.
- `--provider` selects the LLM provider (`openai` or `anthropic`).
- `--model` selects the specific model. Defaults to the provider default.
- `--max-workers` controls how many documents are graded concurrently.
- `--max-tokens` caps the grader response budget per section.

### Output Files

```text
document_scores.csv
section_grades.csv
variable_grades.csv
summary.csv
manifest.json
```

`document_scores.csv` (one row per source document):

- `doc_key`, `intervention_class`, `file_name`: join keys back to the chunker package.
- `overall_grade`, `weighted_score`: roll-up across sections weighted by config.
- `sections_total`, `sections_present`, `sections_missing`: section-level completeness signal.
- `top_issues_json`: ranked top issues across sections and variables.
- `review_status`, `review_error`: `ok` or `error` with message.

`section_grades.csv` (one row per `(doc, section)`):

- `doc_key`, `intervention_class`, `section_name`: join keys.
- `weight`, `grade`, `score`, `is_present`.
- `missing_variables_json`, `issues_json`, `recommendation`.
- `variable_grades_count`.

`variable_grades.csv` (one row per `(doc, section, variable)`):

- `doc_key`, `intervention_class`, `section_name`, `variable_name`.
- `grade`, `score`.
- `issues_json`, `recommendation`.
- `block_ids_json`: source block IDs from the chunker package supporting the variable grade.

`summary.csv`:

- Per-package counts: `documents_total`, `documents_reviewed`, `documents_failed`.
- Aggregate: `average_weighted_score`, `sections_total`.
- Grade distributions: `documents_grade_<G>` and `sections_grade_<G>` for each letter.

`manifest.json`:

- `created_at`, `provider`, `model`, `max_workers`, `max_tokens`.
- `intervention_class`.
- `input_chunker_package`: absolute path to the input package.
- `input_content_blocks_sha256`: hash of the input `content_blocks.csv`, used to detect input drift.
- `documents_total`, `documents_reviewed`, `documents_failed`.

### Joining To Source

The review package is keyed by `doc_key` (joinable to `chunker_package/documents.csv`) and `block_id` (joinable to `chunker_package/content_blocks.csv` for citation). Cross-family or registry-side metadata (dates, owners, therapeutic area) should be joined downstream rather than baked into the review package.

## Design Rules

Load-bearing. Violations break the substrate/app split or duplicate substrate concerns.

1. **PD-specific logic stays in pd_reviewer.** Chunker and (future) evidence remain domain-agnostic. Rubric language, grading prompts, and section weights belong here.
2. **One-way dependency on substrate.** pd_reviewer imports from `chunker` (and will import from `evidence`). The reverse never happens.
3. **One config type, one consumer.** The review config is consumed by the grader. The chunker config path it carries is a *reference*, not a separate type.
4. **Recognition (parsing/labeling) reused, not reimplemented.** pd_reviewer never re-parses or re-labels a document — it calls `chunker.pipeline.run_pipeline`, which orchestrates the chunker's parse + map stages.
5. **Stateless grading.** The grader takes a document + config, returns a review. No persistence; no in-place edits. CLI / UI is the consumer of each run's output.
6. **Provider-neutral LLM access.** Uses its own `llm_client.py` adapter; the LLM client is injected into `chunker.pipeline` rather than imported as a global.

## Current Limitations

- Each section is graded in a single LLM call. Very large sections may need higher `--max-tokens` than the default; reasoning models in particular consume the budget on internal reasoning before emitting output.
- `expertise` was framed as a third quality dimension in the meeting but is not yet implemented in the grader. Today the section grade combines completeness and adherence.
- The review package does not currently include `recommendations.csv` as a long-format table. Recommendations are present per section and per variable in the existing CSVs; flatten downstream if needed.
- Cross-family rollups, time-based slicing, and PST-feedback alignment are downstream analysis concerns and intentionally out of scope for the export package.
