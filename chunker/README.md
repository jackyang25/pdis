# ContentBlock Data Model - Reference

## The Block

Every document gets broken into an ordered list of **ContentBlocks**. One block = one chunk of the document (a paragraph, a heading, or a table row). All blocks use the same schema.

---

## Fields

### Fixed Fields (single values, same shape for every block)

| Field | Type | What it is |
|---|---|---|
| `id` | string | Unique identifier across all documents. Format: `"{doc_id}/b-{ordinal:04d}"`. Used for citations - when a tool points at a specific block, this is the reference. |
| `doc_id` | string | Which document this block came from. Same for every block in a file. Used for filtering/grouping. |
| `ordinal` | int | Position in document order (0, 1, 2...). Used to reconstruct the original sequence. |
| `source_type` | string | What kind of Word element this was: `"heading"`, `"paragraph"`, or `"table_row"`. This is the key that tells you how to read the two composite fields below. |
| `content` | string | The verbatim text. Never modified after parsing. Everything downstream reads this. |
| `heading_stack` | list of strings | The ancestor headings above this block, outermost first. Like breadcrumbs. Example: `["1. Clinical Strategy", "1.2 Endpoints"]`. Built by the parser using a stack - when a new heading at level N appears, everything at level N or deeper gets popped and replaced. |

### Phase 2 Fields (null after parsing, filled by the mapper)

| Field | Type | What it is |
|---|---|---|
| `section_label` | string or null | The normalized section name assigned by the LLM. Example: `"Target Population"`, `"Clinical Endpoints"`. Null until the mapper runs. |
| `label_confidence` | string or null | How confident the LLM was: `"high"`, `"medium"`, or `"low"`. Null until the mapper runs. |

### Composite Fields (dicts, contents vary by `source_type`)

These two fields are both dictionaries whose keys change depending on what kind of block it is. `source_type` tells you which shape to expect.

#### `structural_meta` - "Where did this come from in the file?"

Provenance and traceability. Lets you trace a block back to the exact spot in the source document.

| source_type | Keys | Example |
|---|---|---|
| `heading` | `paragraph_index`, `heading_level` | `{ "paragraph_index": 38, "heading_level": 1 }` |
| `paragraph` | `paragraph_index` | `{ "paragraph_index": 42 }` |
| `table_row` | `table_index`, `row_index`, `column_headers` | `{ "table_index": 2, "row_index": 0, "column_headers": ["Attribute", "Target", "Rationale"] }` |

- `paragraph_index` = which `<w:p>` XML element this was (counter increments for every paragraph the parser walks, even skipped ones)
- `heading_level` = depth in Word's hierarchy (1 = top-level, 2 = subsection, etc.) - drives the heading_stack logic
- `table_index` = which table in the document (0-indexed counter)
- `row_index` = which data row within that table (0-indexed, excludes header row)
- `column_headers` = the first row of the table, so each row block is self-contained and the cells have meaning

#### `style_hint` - "What did it look like in Word?"

Formatting and visual presentation info. Not used by the mapper. Available for downstream tools if they care about formatting.

| source_type | Keys | Example |
|---|---|---|
| `heading` | `style_name`, `is_bold` | `{ "style_name": "Heading 1", "is_bold": false }` |
| `paragraph` | `style_name`, `is_bold` | `{ "style_name": "Normal", "is_bold": true }` |
| `table_row` | `source` | `{ "source": "table_row" }` |
| paragraph (from single-column table) | `source` | `{ "source": "single_column_table" }` |

- `style_name` = the Word style from the ribbon (e.g., "Heading 1", "Normal", "List Paragraph")
- `is_bold` = whether any text run in the paragraph was explicitly bold (note: inherited bold from styles won't show here)
- `source` = for table-derived blocks, records that the block originally came from a table

---

## How the three `source_type` values work

**`heading`** - A Word heading (Heading 1, Heading 2, etc.). Gets added to the heading_stack for all subsequent blocks. Has paragraph-based structural metadata and Word style info.

**`paragraph`** - Normal text content. Also includes single-column table rows and single-cell tables, which Word often uses for layout. These get flattened to paragraphs but their `style_hint.source` records the table origin.

**`table_row`** - A data row from a multi-column table. The header row becomes `column_headers` in structural_meta, and each subsequent row becomes its own block. Content is formatted as `"Header1: Value1, Header2: Value2"`.

---

## What the mapper uses

The mapper (phase 2) only needs a few fields to do its job:

- `source_type` - to know what kind of block it's labeling
- `content` - the actual text
- `heading_stack` - the primary structural signal for section assignment
- `column_headers` (from `structural_meta`, table rows only) - to understand what table cells mean

Everything else is for traceability, debugging, or downstream tools.
