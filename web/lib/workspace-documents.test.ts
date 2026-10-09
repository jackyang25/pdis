import assert from "node:assert/strict";
import test from "node:test";
import type { ContentBlock } from "./api";
import { resolveDocumentVersions, versionTags } from "./workspace-documents.ts";

const block = (doc: string, n: number, content: string): ContentBlock => ({
  id: `${doc}/b-${String(n).padStart(4, "0")}`, doc_id: doc, ordinal: n, block_type: "paragraph", content,
  heading_stack: [], section_label: null, structural_meta: {}, style_hint: {}, image: null,
});
const run = (id: string, text: string) => ({
  id,
  blocks: [block("cTPP", 1, text), block("cTPP", 2, "shared")],
  analysis: { cited_block_ids: ["cTPP/b-0001"], reference_doc_id: "cTPP", note: "cTPP/b-0001 is quoted" },
});

test("the same document read by two runs stays one document", () => {
  const [a, b] = resolveDocumentVersions([run("a", "same"), run("b", "same")]);
  assert.deepEqual(a.blocks.map((x) => x.id), ["cTPP/b-0001", "cTPP/b-0002"]);
  assert.deepEqual(b.blocks.map((x) => x.id), ["cTPP/b-0001", "cTPP/b-0002"]);
});

test("two versions under one name are both kept, each run citing its own", () => {
  const [a, b] = resolveDocumentVersions([run("a", "v1"), run("b", "v2")]);
  assert.notEqual(a.blocks[0].doc_id, b.blocks[0].doc_id);
  for (const version of [a, b]) {
    assert.match(version.blocks[0].doc_id, /^cTPP@[0-9a-f]{6}$/);
    assert.equal(version.blocks[0].id, `${version.blocks[0].doc_id}/b-0001`);
    const analysis = version.analysis as { cited_block_ids: string[]; reference_doc_id: string; note: string };
    assert.deepEqual(analysis.cited_block_ids, [version.blocks[0].id]);
    assert.equal(analysis.reference_doc_id, version.blocks[0].doc_id);
    assert.equal(analysis.note, "cTPP/b-0001 is quoted"); // prose is never rewritten
  }
});

test("the addresses do not depend on the order runs arrive in", () => {
  const forward = resolveDocumentVersions([run("a", "v1"), run("b", "v2")]);
  const backward = resolveDocumentVersions([run("b", "v2"), run("a", "v1")]);
  assert.deepEqual(forward[0].blocks.map((x) => x.id), backward[1].blocks.map((x) => x.id));
});

test("only the document that actually has another version is tagged; a same-run sibling document is untouched", () => {
  const withSibling = (id: string, text: string) => ({
    id,
    blocks: [block("cTPP", 1, text), block("iTPP", 1, "shared")],
    analysis: {},
  });
  const [a, b] = resolveDocumentVersions([withSibling("a", "v1"), withSibling("b", "v2")]);
  for (const version of [a, b]) {
    assert.match(version.blocks[0].doc_id, /^cTPP@[0-9a-f]{6}$/);
    assert.equal(version.blocks[1].doc_id, "iTPP");
    assert.equal(version.blocks[1].id, "iTPP/b-0001");
  }
});

test("versionTags falls back to the full fingerprint for every version once two of them share a tag", () => {
  const a = "00000000abc123";
  const b = "11111111abc123";
  const c = "22222222def456";
  const tags = versionTags([a, b, c]);
  assert.equal(tags.get(a), a);
  assert.equal(tags.get(b), b);
  assert.equal(tags.get(c), c);
});

test("versionTags keeps the short low-digit tag when nothing collides", () => {
  const a = "00000000abc123";
  const b = "11111111ef4567";
  const tags = versionTags([a, b]);
  assert.equal(tags.get(a), "abc123");
  assert.equal(tags.get(b), "ef4567");
});
