# Document Chunker

The chunker turns `.docx` files into ordered, citable `ContentBlock` objects, then optionally runs an LLM mapper that assigns normalized section labels.

The pipeline has two explicit phases:

1. **Parser**: deterministic `.docx` parsing. Produces blocks with source text, document order, heading context, and structural provenance.
2. **Mapper**: LLM-driven section labeling. Adds `section_label` and `label_confidence` using a document-type config.

The Streamlit app is a local inspector for this flow. It has a single-document mode for deep inspection and a batch parser mode for comparing parser behavior across multiple TPP documents.

## Files

| File | Purpose |
|---|---|
| `models.py` | Shared dataclasses: `ContentBlock` and `DocumentTypeConfig`; YAML config loader. |
| `parser.py` | Deterministic Word parser. Walks XML body order so paragraphs and tables stay interleaved correctly. |
| `mapper.py` | Prompt builder, provider-specific LLM calls, JSON validation, and label merge. |
| `app.py` | Streamlit UI for single-document inspection and batch parser evaluation. |
| `configs/tpp_vaccine.yaml` | First mapper config: Vaccine TPP taxonomy, preamble, and disambiguation rules. |
| `requirements.txt` | Runtime dependencies. |

## Running The App

From the repo root:

```bash
source .venv/bin/activate
python -m pip install -r chunker/requirements.txt
python -m streamlit run chunker/app.py
```

The app has two modes.

### Single Document Inspector

This mode is for inspecting one document deeply.

1. Upload a `.docx`.
2. Click **Parse Document** to create raw `ContentBlock`s.
3. Review parser output.
4. Choose an LLM provider, enter that provider's API key, and click **Run Mapper** if section labels are needed.
5. Download JSON. Before mapping, mapper fields are `null`; after mapping, they are filled.

### Batch Parser Evaluation

This mode is for comparing parser behavior across multiple TPP files and optionally mapping all parsed documents.

1. Select **Batch Parser Evaluation** in the sidebar.
2. Upload multiple `.docx` files.
3. Click **Parse All Documents**.
4. Review per-document metrics and block previews.
5. Optionally choose an LLM provider, enter that provider's API key, and click **Run Mapper On Batch**.
6. Download `batch_summary.csv` or `batch_blocks.json`.

Parsing and mapping are both parallelized in batch mode. Mapper failures are isolated per document so one failed API call does not discard the rest of the batch.

## ContentBlock Schema

Every document is broken into an ordered list of `ContentBlock`s. One block represents one chunk of the document: a heading, paragraph, or table row. All blocks use the same top-level schema.

| Field | Type | Set by | What it is |
|---|---|---|---|
| `id` | string | Parser | Unique citation ID. Format: `"{doc_id}/b-{ordinal:04d}"`. |
| `doc_id` | string | Parser | Source document identifier. |
| `ordinal` | int | Parser | Position in document order, 0-indexed. |
| `source_type` | string | Parser | One of `"heading"`, `"paragraph"`, or `"table_row"`. |
| `content` | string | Parser | Verbatim block text. |
| `heading_stack` | list of strings | Parser | Ancestor headings, outermost first. |
| `structural_meta` | dict | Parser | Provenance fields. Shape varies by `source_type`. |
| `style_hint` | dict | Parser | Formatting/source hints. Shape varies by origin. |
| `section_label` | string or null | Mapper | Normalized section label. Null until mapper runs. |
| `label_confidence` | string or null | Mapper | `"high"`, `"medium"`, or `"low"`. Null until mapper runs. |

### `structural_meta`

`structural_meta` answers: "Where did this block come from in the Word file?"

| Block kind | Keys | Example |
|---|---|---|
| Heading | `paragraph_index`, `heading_level` | `{ "paragraph_index": 38, "heading_level": 1 }` |
| Normal paragraph | `paragraph_index` | `{ "paragraph_index": 42 }` |
| Single-cell table paragraph | `table_index`, `row_index` | `{ "table_index": 0, "row_index": 0 }` |
| Single-column table paragraph | `table_index`, `row_index` | `{ "table_index": 0, "row_index": 2 }` |
| Multi-column table row | `table_index`, `row_index`, `column_headers` | `{ "table_index": 2, "row_index": 1, "column_headers": ["Variable", "Minimum", "Optimistic"] }` |

Notes:

- `paragraph_index` increments for every `<w:p>` element walked, including skipped empty paragraphs.
- `heading_level` is structural, so it lives only in `structural_meta`, not `style_hint`.
- `table_index` is the 0-indexed table position in the document.
- `row_index` is the row position within that table.
- `column_headers` stores the first row of a multi-column table so each `table_row` block is self-contained.

### `style_hint`

`style_hint` answers: "What did this look like, or what parser path produced it?"

| Origin | Keys | Example |
|---|---|---|
| Heading paragraph | `style_name`, `is_bold` | `{ "style_name": "Heading 1", "is_bold": false }` |
| Normal paragraph | `style_name`, `is_bold` | `{ "style_name": "Normal", "is_bold": true }` |
| Table row | `source` | `{ "source": "table_row" }` |
| Single-column table paragraph | `source` | `{ "source": "single_column_table" }` |
| Single-cell table paragraph | `source` | `{ "source": "single_cell_table" }` |
| Header-only table paragraph | `source` | `{ "source": "table_headers" }` |

`is_bold` checks explicit run-level bold only. Bold inherited from a Word style may not appear here.

## Parser Behavior

The parser walks `doc.element.body` in XML order, not `doc.paragraphs`, so interspersed tables stay in the correct document sequence.

For paragraphs:

- Empty paragraphs are skipped, but still count toward `paragraph_index`.
- Word styles starting with `"Heading"` become `source_type="heading"`.
- Non-heading paragraphs become `source_type="paragraph"`.
- The parser maintains a heading stack. When a heading at level `N` appears, headings at level `N` or deeper are popped and the new heading is pushed.

For tables:

- **Single-cell table**: flattened into one paragraph block with `style_hint.source="single_cell_table"`.
- **Single-column table**: each non-empty row becomes one paragraph block with `style_hint.source="single_column_table"`.
- **Multi-column table**: first row becomes `column_headers`; each subsequent non-empty row becomes one `table_row` block.
- **Header-only multi-column table**: emitted as a paragraph block with headers joined by `" | "` and `style_hint.source="table_headers"`.
- **Merged/repeated cells**: repeated values are preserved in the row output so each block remains self-contained.

## Batch Parser Evaluation

Batch mode helps answer whether the parser and mapper perform consistently across clean, messy, and table-heavy TPPs.

After parsing, the app reports:

- `doc_id`
- `file_name`
- `total_blocks`
- `heading_count`
- `paragraph_count`
- `table_row_count`
- `single_column_table_blocks`
- `single_cell_table_blocks`
- `table_count`
- `has_headings`
- `has_tables`

Use these metrics to spot parser problems before running the mapper. For example:

- Very low `heading_count` may mean the document does not use Word heading styles.
- Very low `table_row_count` on a table-heavy TPP may mean tables were formatted as single-column layout tables or unusual Word structures.
- High `single_column_table_blocks` often means the document uses tables for layout rather than data tables.
- `has_tables=false` on a TPP that visibly contains tables is a parser investigation target.

Batch downloads:

- `batch_summary.csv`: one row per document with parser metrics.
- `batch_blocks.json`: all parsed blocks grouped by document, including metrics and full `ContentBlock` dictionaries.

If **Run Mapper On Batch** is used, the app maps documents in parallel and adds label metrics to the summary:

- `unlabeled_count`
- `mapping_error_count`
- `document_metadata_count`
- `low_confidence_count`
- `medium_confidence_count`
- `high_confidence_count`
- `average_confidence`

Batch mapper errors are shown in a separate table. Documents that map successfully keep their labels; documents that fail keep their parsed blocks and include `mapper_error` in the combined JSON.

## Table Reconstruction

Tables are not stored as nested table objects after chunking. They are represented as ordered blocks with enough metadata to group and interpret rows.

To reconstruct a multi-column table view:

1. Select blocks where `source_type == "table_row"`.
2. Group by `structural_meta["table_index"]`.
3. Sort each group by `structural_meta["row_index"]`.
4. Use `structural_meta["column_headers"]` as the table columns.
5. Use each block's `content` as a readable row summary, or parse from the `"Header: Value"` pairs if a display table is needed.

Example table row block:

```json
{
  "source_type": "table_row",
  "content": "Variable: Indication, Minimum: Prevention of disease, Optimistic: Broader protection",
  "structural_meta": {
    "table_index": 2,
    "row_index": 1,
    "column_headers": ["Variable", "Minimum", "Optimistic"]
  },
  "style_hint": {
    "source": "table_row"
  }
}
```

Single-column and single-cell tables are intentionally flattened to paragraph blocks because Word often uses them for layout. They can be grouped by `table_index`, but they are not treated as data tables.

## Mapper Config

The mapper is driven by a `DocumentTypeConfig` loaded from YAML.

Current config:

```text
configs/tpp_vaccine.yaml
```

It defines:

- `type_key`: machine-readable config key.
- `display_name`: UI label.
- `section_taxonomy`: document-specific section definitions. Each entry has `name` and `description`.
- `preamble`: document-type context injected into the system prompt.
- `disambiguation`: rules for ambiguous blocks.
- `include_metadata_label`: whether the engine injects `Document Metadata`.
- `include_other_label`: whether the engine injects `Other`.

The current TPP document-specific taxonomy includes:

- `Introduction`
- `Instructions for Use`
- `Medical Need / Use Case`
- `Executive Summary (Core Variables)`
- `Additional Variables of Interest`
- `Change Management`

The mapper engine appends universal labels when enabled:

- `Document Metadata`: page numbers, version stamps, template metadata, headers, footers, and formatting artifacts.
- `Other`: real content that does not fit any document-specific section.

The mapper accepts `Other` only as an exact label. Free-text variants like `Other: Reviewer note` are not valid.

## Mapper Prompt Format

Prompt construction is split into two messages: a system prompt and a user message.

### System Prompt

The system prompt is assembled from:

1. Base labeling instructions.
2. The config `preamble`.
3. The final taxonomy as a definition list: document-specific labels plus descriptions, followed by enabled universal labels.
4. The config disambiguation rules plus enabled standard universal-label rules.
5. Strict JSON output instructions.

The output format requested from the LLM is:

```json
[
  {"id": "doc-001/b-0000", "section_label": "Introduction", "confidence": "high"},
  {"id": "doc-001/b-0001", "section_label": "Introduction", "confidence": "high"}
]
```

Every input block ID must appear exactly once. `confidence` must be one of `"high"`, `"medium"`, or `"low"`.

### User Message

The user message is a compact ordered list of blocks.

Paragraph block:

```text
[my-doc/b-0001 | paragraph | headings: "1. Clinical Strategy" > "1.2 Endpoints"]
<content>The primary endpoint is...</content>
```

Table row block:

```text
[my-doc/b-0005 | table_row | headings: "Executive Summary" | cols: Variable, Minimum, Optimistic, Annotations]
<content>Variable: Indication, Minimum: Vaccine is indicated for..., Optimistic: ..., Annotations: ...</content>
```

Heading block:

```text
[my-doc/b-0003 | heading | level: 1]
<content>Executive Summary with Annotations</content>
```

The mapper primarily uses:

- `source_type`
- `content`
- `heading_stack`
- `structural_meta.column_headers` for table rows
- the config taxonomy and disambiguation rules

## Mapper Validation And Merge

After the LLM returns JSON, `mapper.py`:

1. Strips markdown fences if present.
2. Parses the JSON response.
3. Checks for missing, duplicate, and unexpected block IDs.
4. Checks whether labels are exact matches in the final taxonomy.
5. Checks confidence values.
6. Merges labels back into the original `ContentBlock` objects.

Failure behavior:

- If the first LLM response is invalid JSON, the mapper retries once.
- If the retry is also invalid JSON, the mapper raises `MapperResponseError` and the UI reports a document-level mapper failure.
- If some block IDs are missing from a valid response, only those missing blocks become `Mapping Error` with low confidence.
- Invalid labels or confidence values become `Mapping Error` with low confidence.

## LLM Provider Handling

The Streamlit app lets you choose the mapper provider in the sidebar:

- `anthropic`, default model `claude-opus-4-7`
- `openai`, default model `gpt-5.5`

The selected provider, model, and API key are passed from `app.py` to `label_blocks()`. Prompt construction, JSON parsing, validation, and merge behavior stay shared; only the final LLM call is provider-specific.

The key is not stored by the app and should not be committed. Keep local secrets in ignored files such as `.env` if you add environment loading later.

## Current Limitations

- The mapper sends all blocks for a document in one request. For 200+ blocks, it logs a warning but still attempts the call.
- Intra-document mapper batching is not implemented yet.
- Table reconstruction is metadata-based; original Word table styling, merged-cell geometry, and exact grid layout are not preserved.
