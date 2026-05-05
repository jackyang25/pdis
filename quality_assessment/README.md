# Document Quality Assessment

Document Quality Assessment evaluates document completeness and adherence against a document-type rubric, then produces a graded report card. The bundled TPP configs currently cover vaccine, drug, diagnostic, and medical device TPPs.

It uses the chunker as a library for document parsing and section labeling, then runs assessment prompts over the labeled content.

## Architecture

The module is intentionally separate from the chunker UI and LLM adapter.

- `app.py`: Streamlit view and standalone entrypoint.
- `assessor.py`: End-to-end orchestration.
- `evaluator.py`: LLM prompt construction, JSON parsing, and section grading.
- `models.py`: Assessment config, rubric, and report dataclasses.
- `llm_client.py`: Document Quality Assessment LLM adapter.
- `configs/`: Document-type assessment rubrics.

Document Quality Assessment imports chunker parsing and mapping APIs:

- `chunker.parser.parse_document`
- `chunker.mapper.label_blocks`
- `chunker.models.load_config`

Document Quality Assessment provides its own LLM client and injects it into the chunker mapper. This keeps it independently distributable while still reusing chunker logic.

## Setup

From the repository root:

```bash
source .venv/bin/activate
python -m pip install -r chunker/requirements.txt
python -m pip install -r quality_assessment/requirements.txt
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
streamlit run app.py
```

Or run Document Quality Assessment directly:

```bash
streamlit run quality_assessment/app.py
```

## Assessment Config

Assessment behavior is driven by YAML, not hardcoded logic. Bundled configs include:

```text
quality_assessment/configs/tpp_vaccine.yaml
quality_assessment/configs/tpp_drug_assessment.yaml
quality_assessment/configs/tpp_diagnostic_assessment.yaml
quality_assessment/configs/tpp_device_assessment.yaml
```

The config defines:

- `type_key`: Stable document-type key.
- `display_name`: UI label.
- `chunker_config_path`: Chunker taxonomy config to use for labeling.
- `sections`: Ordered section rubric with section names, descriptions, weights, and expected variables.

Section names must match the chunker's `section_label` taxonomy.

## How Grading Works

The grading flow has three layers:

1. Chunker parses the uploaded document into blocks and labels each block with a section using the selected LLM client.
2. Document Quality Assessment evaluates each configured section with the selected LLM.
3. The overall grade is computed from section grades using the weights in the config.

For sections with expected variables, such as a TPP executive summary table, the evaluator asks the LLM to:

- determine which expected variables are present
- list missing variables
- grade each present variable
- return source `block_ids` for each variable grade
- assign a section grade based on completeness and adherence

For prose sections with no expected variables, the evaluator returns only a section-level grade, issues, and recommendation.

The section grade is returned by the LLM. It is not computed as a simple average of variable grades, because the section may include broader context, prose, notes, or structural issues. The overall document grade is deterministic: section grades are converted to numeric scores and weighted by each section's configured `weight`.

## Output

The assessment returns an `AssessmentResult` with:

- `doc_id`
- `overall_grade`
- `top_issues`
- `section_grades`

Each section grade includes:

- section-level grade
- whether the section is present
- missing variables
- issues
- recommendation
- per-variable grades with source `block_ids`

The UI includes a download button for the full JSON report.
