import assert from "node:assert/strict";
import test from "node:test";
import type { ContentBlock } from "./api.ts";
import { documentBlockLocationLabel, documentExtractionWarnings } from "./document-extraction.ts";

function block(doc_id: string, meta = {}): ContentBlock {
  return { id: `${doc_id}/b-0001`, doc_id, ordinal: 1, content: "Text", block_type: "paragraph",
    heading_stack: [], section_label: null, structural_meta: meta, style_hint: {} };
}

test("extraction warnings account for each document once, never infer them from filenames", () => {
  assert.deepEqual(documentExtractionWarnings([
    block("report", { extraction_warnings: ["pdf_text_only"] }),
    block("report", { extraction_warnings: ["pdf_text_only"] }),
    block("notes", { extraction_warnings: ["pdf_text_only"] }),
    block("paper.pdf"),
  ]), [{ code: "pdf_text_only", documentIds: ["report", "notes"] }]);
  assert.deepEqual(documentExtractionWarnings([block("paper.pdf")]), []);
});

test("locations use declared page numbers and retain existing section fallback", () => {
  assert.equal(documentBlockLocationLabel(block("report", { page: 7 })), "Page 7");
  for (const page of [0, -1, 1.5, "7", null]) {
    assert.equal(documentBlockLocationLabel(block("report", { page })), "");
  }
  const heading = block("plan");
  heading.heading_stack = ["Objectives"];
  assert.equal(documentBlockLocationLabel(heading), "Objectives");
  heading.section_label = "Clinical";
  assert.equal(documentBlockLocationLabel(heading), "Clinical");
});
