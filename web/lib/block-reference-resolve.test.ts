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

test("a shortened id does not resolve", () => {
  // The model writes the full ID; a tolerant match was added for a failure that
  // turned out to be percent-encoding, and it hid whether the real form worked.
  assert.equal(resolveBlock(blocks, "b-0080"), null);
});

test("surrounding whitespace does not prevent a match", () => {
  assert.equal(resolveBlock(blocks, `  ${DOC}/b-0080  `)?.id, `${DOC}/b-0080`);
});

test("an id from another document does not resolve", () => {
  const twoDocs = [{ id: "one/b-0080" }, { id: "two/b-0080" }];
  assert.equal(resolveBlock(twoDocs, "three/b-0080"), null);
});

test("an id the workspace does not hold resolves to nothing", () => {
  assert.equal(resolveBlock(blocks, "b-9999"), null);
  assert.equal(resolveBlock(blocks, ""), null);
});

test("a partial id is not a match", () => {
  assert.equal(resolveBlock(blocks, `${DOC}/b-008`), null);
});
