/**
 * Which block a citation opens.
 *
 * A block ID carries the document name — `DRAFT AIV iTPP v1 13July2016/b-0080` —
 * so the full form is long and the model cites the short tail instead. That is a
 * real reference, not a malformed one, and refusing it left a citation rendering
 * as plain text with no way for a reader to tell why.
 *
 * Resolution stays deterministic: a tail is accepted only when exactly one block
 * ends with it.
 */

import assert from "node:assert/strict";
import test from "node:test";

import { resolveBlock } from "./block-reference.ts";

const DOC = "DRAFT AIV iTPP v1 13July2016";
const blocks = [
  { id: `${DOC}/b-0000` },
  { id: `${DOC}/b-0080` },
  { id: `${DOC}/b-0097` },
];

test("an exact id resolves", () => {
  assert.equal(resolveBlock(blocks, `${DOC}/b-0080`)?.id, `${DOC}/b-0080`);
});

test("a shortened id resolves when only one block ends with it", () => {
  // What the model actually writes, and what a reader sees on screen.
  assert.equal(resolveBlock(blocks, "b-0080")?.id, `${DOC}/b-0080`);
});

test("surrounding whitespace does not prevent a match", () => {
  assert.equal(resolveBlock(blocks, "  b-0080  ")?.id, `${DOC}/b-0080`);
});

test("a tail shared by two documents resolves to neither", () => {
  // Genuinely ambiguous, so it renders as text rather than opening the wrong
  // passage — a citation pointing at the wrong evidence is worse than none.
  const twoDocs = [{ id: "one/b-0080" }, { id: "two/b-0080" }];
  assert.equal(resolveBlock(twoDocs, "b-0080"), null);
});

test("an id the workspace does not hold resolves to nothing", () => {
  assert.equal(resolveBlock(blocks, "b-9999"), null);
  assert.equal(resolveBlock(blocks, ""), null);
});

test("a partial tail is not a match", () => {
  // Only a whole trailing segment counts, so "080" never resolves "b-0080".
  assert.equal(resolveBlock(blocks, "080"), null);
});
