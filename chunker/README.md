# Document Chunker

The chunker turns `.docx` files into ordered, citable `ContentBlock` objects, then optionally runs an LLM mapper that assigns normalized section labels.

The pipeline has two explicit phases:

1. **Parser**: deterministic `.docx` parsing. Produces blocks with source text, document order, heading context, and structural provenance.
2. **Mapper**: LLM-driven section labeling. Adds `section_label` and `label_confidence` using a document-type config.

The Streamlit app is a local inspector for this flow: upload a document, click **Parse Document**, review parser output, then optionally click **Run Mapper**.

## Files

| File | Purpose |
|---|---|
| `models.py` | Shared dataclasses: `ContentBlock` and `DocumentTypeConfig`; YAML config loader. |
| `parser.py` | Deterministic Word parser. Walks XML body order so paragraphs and tables stay interleaved correctly. |
| `mapper.py` | Prompt builder, Anthropic call, JSON validation, and label merge. |
| `app.py` | Streamlit UI for inspecting parser output and optional mapper output. |
| `configs/tpp_vaccine.yaml` | First mapper config: Vaccine TPP taxonomy, preamble, and disambiguation rules. |
| `requirements.txt` | Runtime dependencies. |

## Running The App

From the repo root:

```bash
source .venv/bin/activate
python -m pip install -r chunker/requirements.txt
python -m streamlit run chunker/app.py
```

The UI sequence is intentional:

1. Upload a `.docx`.
2. Click **Parse Document** to create raw `ContentBlock`s.
3. Review parser output.
4. Enter an Anthropic API key and click **Run Mapper** if section labels are needed.
5. Download JSON. Before mapping, mapper fields are `null`; after mapping, they are filled.

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
- `section_taxonomy`: canonical labels the mapper should use.
- `preamble`: document-type context injected into the system prompt.
- `disambiguation`: rules for ambiguous blocks.
- `allow_other`: whether `"Other: ..."` labels are allowed.

The current TPP taxonomy includes:

- `Introduction`
- `Instructions for Use`
- `Medical Need / Use Case`
- `Executive Summary (Core Variables)`
- `Additional Variables of Interest`
- `Change Management`
- `Document Metadata`

`Document Metadata` is for page numbers, version stamps, template metadata, headers, footers, and formatting artifacts.

## Mapper Prompt Format

Prompt construction is split into two messages: a system prompt and a user message.

### System Prompt

The system prompt is assembled from:

1. Base labeling instructions.
2. The config `preamble`.
3. The config taxonomy as a numbered list.
4. The config disambiguation rules as bullets.
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
3. Checks for missing, duplicate, and unknown block IDs.
4. Checks whether labels are in the configured taxonomy, or match `"Other: ..."` when allowed.
5. Checks confidence values.
6. Merges labels back into the original `ContentBlock` objects.

Failure behavior:

- If the first LLM response is invalid JSON, the mapper retries once.
- If the retry is also invalid JSON, all blocks are labeled `Unknown` with low confidence.
- If some block IDs are missing from a valid response, only those missing blocks become `Unknown` with low confidence.
- Invalid labels are kept but logged as warnings so review can continue.

## API Key Handling

The Streamlit app asks for the Anthropic API key in the sidebar. The key is passed from `app.py` to `label_blocks()` and then into `anthropic.Anthropic(api_key=api_key)`.

The key is not stored by the app and should not be committed. Keep local secrets in ignored files such as `.env` if you add environment loading later.

## Current Limitations

- The app currently supports one uploaded document at a time.
- The mapper sends all blocks in one request. For 200+ blocks, it logs a warning but still attempts the call.
- No batching or cross-document comparison harness exists yet.
- Table reconstruction is metadata-based; original Word table styling, merged-cell geometry, and exact grid layout are not preserved.
