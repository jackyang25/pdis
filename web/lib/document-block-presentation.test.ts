import assert from "node:assert/strict";
import test from "node:test";

import type { ContentBlock } from "./api.ts";
import {
  documentBlockPresentation,
  documentBlockSpacing,
  documentTableCells,
  documentTracePanelMode,
  documentTraceRailMode,
} from "./document-block-presentation.ts";

function contentBlock(
  blockType: ContentBlock["block_type"],
  structuralMeta: Record<string, unknown>,
  content = "Source-authored content",
): ContentBlock {
  return {
    id: `document/${blockType}`,
    doc_id: "document",
    ordinal: 1,
    block_type: blockType,
    content,
    heading_stack: [],
    section_label: null,
    structural_meta: structuralMeta,
    style_hint: {},
    image: null,
  };
}

test("maps canonical heading levels to a restrained hierarchy", () => {
  assert.equal(
    documentBlockPresentation(contentBlock("heading", { heading_level: 1 })),
    "heading-primary",
  );
  assert.equal(
    documentBlockPresentation(contentBlock("heading", { heading_level: 2 })),
    "heading-secondary",
  );
  assert.equal(
    documentBlockPresentation(contentBlock("heading", { heading_level: 4 })),
    "heading-tertiary",
  );
});

test("falls back safely and preserves table rows as one visual record", () => {
  assert.equal(
    documentBlockPresentation(contentBlock("heading", {})),
    "heading-secondary",
  );
  assert.equal(
    documentBlockPresentation(contentBlock("heading", { heading_level: "1" })),
    "heading-secondary",
  );
  assert.equal(
    documentBlockPresentation(contentBlock("table_row", { row_index: 2 })),
    "table-row",
  );
  assert.equal(
    documentBlockPresentation(contentBlock("paragraph", {})),
    "body",
  );
});

test("places trace controls outside the paper only when space permits", () => {
  assert.equal(documentTraceRailMode(1024), "external");
  assert.equal(documentTraceRailMode(720), "external");
  assert.equal(documentTraceRailMode(639), "inline");
});

test("uses one shared vertical rhythm for gutter and source content", () => {
  assert.equal(documentBlockSpacing("heading-primary"), "major");
  assert.equal(documentBlockSpacing("heading-secondary"), "section");
  assert.equal(documentBlockSpacing("heading-tertiary"), "subsection");
  assert.equal(documentBlockSpacing("body"), "body");
  assert.equal(documentBlockSpacing("table-row"), "continuation");
});

test("accepts only parser-owned table cells whose offsets match canonical content", () => {
  const content = "Measure: Efficacy, Target: >= 75%";
  const valid = contentBlock("table_row", {
    column_headers: ["Measure", "Target"],
    table_cells: [
      {
        column_index: 0,
        header: "Measure",
        value: "Efficacy",
        content_start: 0,
        content_end: 17,
        value_start: 9,
        value_end: 17,
      },
      {
        column_index: 1,
        header: "Target",
        value: ">= 75%",
        content_start: 19,
        content_end: 33,
        value_start: 27,
        value_end: 33,
      },
    ],
  }, content);

  assert.deepEqual(documentTableCells(valid), {
    columnCount: 2,
    cells: [
      {
        columnIndex: 0,
        header: "Measure",
        value: "Efficacy",
        contentStart: 0,
        contentEnd: 17,
        valueStart: 9,
        valueEnd: 17,
      },
      {
        columnIndex: 1,
        header: "Target",
        value: ">= 75%",
        contentStart: 19,
        contentEnd: 33,
        valueStart: 27,
        valueEnd: 33,
      },
    ],
  });

  const parserWhitespace = contentBlock("table_row", {
    column_headers: [" Measure "],
    table_cells: [
      {
        column_index: 0,
        header: "Measure",
        value: "Efficacy",
        content_start: 0,
        content_end: 17,
        value_start: 9,
        value_end: 17,
      },
    ],
  }, "Measure: Efficacy");
  assert.equal(documentTableCells(parserWhitespace)?.cells[0]?.header, "Measure");

  const invalid = structuredClone(valid);
  (invalid.structural_meta.table_cells as Array<Record<string, unknown>>)[0].value_end = 16;
  assert.equal(documentTableCells(invalid), null);
  assert.equal(documentTableCells(contentBlock("paragraph", {}, content)), null);
});

test("the details panel goes beside the document whenever both columns fit", () => {
  // 1056px is the widest container any page can hand the trace: the app shell caps
  // content at 1120 and spends 64 on padding. The old threshold was 1024, ~30px under
  // that ceiling, so a scrollbar's width decided whether a full-screen window showed a
  // panel or a bottom sheet — and two tools disagreed with nothing visible to explain
  // it. These are the widths that actually exist.
  assert.equal(documentTracePanelMode(1056), "aside");
  assert.equal(documentTracePanelMode(1024), "aside");
  assert.equal(documentTracePanelMode(1041), "aside");
});

test("it covers the document only when there is genuinely no room beside it", () => {
  // 352 for the panel plus 448 for a readable document column.
  assert.equal(documentTracePanelMode(800), "aside");
  assert.equal(documentTracePanelMode(799), "sheet");
  assert.equal(documentTracePanelMode(420), "sheet");
});

test("an unmeasured container covers the document rather than guessing", () => {
  // Zero is what the first render reports before the observer fires.
  assert.equal(documentTracePanelMode(0), "sheet");
  assert.equal(documentTracePanelMode(Number.NaN), "sheet");
});
