import assert from "node:assert/strict";
import test from "node:test";
import type { ContentBlock } from "./api.ts";
import { groupDocumentTraceSurfaces } from "./document-trace-surfaces.ts";
import { documentBlockLocationLabel } from "./document-extraction.ts";
import { buildDocumentTrace, documentTraceBlockLocation, documentTracePassages } from "./document-trace.ts";

function item(id: string, metadata: Record<string, unknown> = {}, type = "paragraph") {
  const block: ContentBlock = {
    id, doc_id: id.split("/")[0], ordinal: 1, block_type: type,
    content: `Text of ${id}`, heading_stack: [], section_label: null,
    structural_meta: metadata, style_hint: {},
  };
  return { block };
}

test("consecutive PDF pages form separate surfaces without renumbering or filling gaps", () => {
  const blocks = [item("doc/a", { page: 2 }), item("doc/b", { page: 2 }), item("doc/c", { page: 5 })];
  const surfaces = groupDocumentTraceSurfaces(blocks);
  assert.deepEqual(surfaces.map((s) => s.boundary?.label), ["Page 2", "Page 5"]);
  assert.deepEqual(surfaces.map((s) => s.blocks.map((b) => b.block.id)), [["doc/a", "doc/b"], ["doc/c"]]);
  assert.equal(surfaces[0].blocks[0], blocks[0]);
});

test("all slide content stays together including notes and the full-slide visual", () => {
  const blocks = [item("deck/a", { slide: 1 }, "heading"), item("deck/b", { slide: 1 }, "table_row"),
    item("deck/c", { slide: 1, speaker_notes: true }),
    item("deck/d", { slide: 1, visual_scope: "full_slide" }, "image"), item("deck/e", { slide: 2 })];
  const surfaces = groupDocumentTraceSurfaces(blocks);
  assert.deepEqual(surfaces.map((s) => s.boundary?.label), ["Slide 1", "Slide 2"]);
  assert.deepEqual(surfaces[0].blocks, blocks.slice(0, 4));
  assert.equal(documentBlockLocationLabel(blocks[0].block), "Slide 1");
});

test("Word and legacy blocks stay continuous without guessing boundaries from text or headings", () => {
  const blocks = [item("word/a"), item("word/b", {}, "heading"), item("word/c")];
  blocks[1].block.content = "Page 2 / Slide 3";
  blocks[1].block.heading_stack = ["Section 2"];
  const surfaces = groupDocumentTraceSurfaces(blocks);
  assert.equal(surfaces.length, 1);
  assert.equal(surfaces[0].boundary, null);
  assert.deepEqual(surfaces[0].blocks, blocks);
  assert.deepEqual(groupDocumentTraceSurfaces([]), []);
});

test("missing, invalid or conflicting metadata is not assigned a neighboring page", () => {
  for (const metadata of [{}, { page: "1" }, { page: 0 }, { slide: -1 }, { page: 1.5 }, { page: 1, slide: 1 }]) {
    const surfaces = groupDocumentTraceSurfaces([item("doc/a", { page: 1 }), item("doc/b", metadata), item("doc/c", { page: 1 })]);
    assert.deepEqual(surfaces.map((s) => s.boundary?.label ?? null), ["Page 1", null, "Page 1"]);
  }
});

test("grouping never sorts blocks or merges nonconsecutive, different-kind or different-document boundaries", () => {
  const blocks = [item("doc/a", { page: 2 }), item("doc/b", { page: 1 }), item("doc/c", { slide: 1 }),
    item("other/d", { slide: 1 }), item("doc/e", { page: 2 })];
  const surfaces = groupDocumentTraceSurfaces(blocks);
  assert.equal(surfaces.length, 5);
  assert.deepEqual(surfaces.flatMap((s) => s.blocks), blocks);
  assert.equal(new Set(surfaces.map((s) => s.key)).size, 5);
});

test("grouping keeps citation targets, exact highlights and passage navigation intact", () => {
  const blocks = [item("deck/a", { slide: 1 }).block, item("deck/b", { slide: 2 }).block];
  const trace = buildDocumentTrace(blocks, [{
    id: "finding", kind: "finding", layerLabel: "Finding", title: "Finding", summary: "Summary",
    blockIds: ["deck/b"], spans: [{ quote: "Text of deck/b", blockIds: ["deck/b"] }], sourceRef: {},
  }]);
  const surfaces = groupDocumentTraceSurfaces(trace.documents[0].blocks);
  assert.equal(surfaces[1].blocks[0], trace.documents[0].blocks[1]);
  assert.equal(surfaces[1].blocks[0].segments[0].annotationIds[0], "finding");
  assert.deepEqual(documentTraceBlockLocation(trace, "deck/b"), { documentId: "deck", annotationIds: ["finding"] });
  assert.equal(documentTracePassages(trace, "finding")[0].sectionLabel, "Slide 2");
});
