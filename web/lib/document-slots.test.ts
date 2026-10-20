import assert from "node:assert/strict";
import test from "node:test";
import { documentIdentity, placeFiles } from "./document-slots.ts";

const SUFFIXES = [".docx", ".pptx", ".pdf"];
const file = (name: string) => new File(["x"], name);
const names = (record: Record<string, File>) =>
  Object.fromEntries(Object.entries(record).map(([id, held]) => [id, held.name]));

test("a drop fills the slot it landed on, then the empty slots, then asks for new ones", () => {
  const result = placeFiles({
    slotId: "b",
    picked: [file("one.docx"), file("two.pptx"), file("three.pdf"), file("four.docx")],
    slotIds: ["a", "b", "c"],
    held: { a: file("held.docx") },
    suffixes: SUFFIXES,
  });
  assert.deepEqual(names(result.placed), { b: "one.docx", c: "two.pptx" });
  assert.deepEqual(result.overflow.map((held) => held.name), ["three.pdf", "four.docx"]);
});

test("a file the tool cannot read, or a second file of one name, is refused by name", () => {
  const result = placeFiles({
    slotId: "a",
    picked: [file("notes.txt"), file("plan.docx"), file("plan.pdf"), file("held.pptx")],
    slotIds: ["a", "b"],
    held: { b: file("held.docx") },
    suffixes: SUFFIXES,
  });
  assert.deepEqual(names(result.placed), { a: "plan.docx" });
  assert.deepEqual(result.unsupported, ["notes.txt"]);
  // Identity is the stem, as the server's is, so a format change does not make a new document.
  assert.deepEqual(result.repeated, ["plan.pdf", "held.pptx"]);
  assert.deepEqual(result.overflow, []);
});

test("replacing a slot's file frees its name for the replacement", () => {
  const result = placeFiles({
    slotId: "a",
    picked: [file("plan.pptx")],
    slotIds: ["a"],
    held: { a: file("plan.docx") },
    suffixes: SUFFIXES,
  });
  assert.deepEqual(names(result.placed), { a: "plan.pptx" });
  assert.deepEqual(result.repeated, []);
});

test("identity drops only the last extension, as the server's filename stem does", () => {
  assert.equal(documentIdentity("2026-09-05 Truepoc_SG2_[v20260905]_PREREAD.pptx"), "2026-09-05 Truepoc_SG2_[v20260905]_PREREAD");
  assert.equal(documentIdentity("plan.v2.docx"), "plan.v2");
});
