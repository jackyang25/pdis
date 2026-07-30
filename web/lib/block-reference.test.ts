import assert from "node:assert/strict";
import test from "node:test";

import {
  blockReferenceLabel,
  compactBlockId,
  sourcePassageAriaLabel,
} from "./block-reference.ts";

test("keeps the canonical ID while deriving one compact visible ID", () => {
  assert.equal(compactBlockId("DRAFT AIV/b-0040"), "b-0040");
  assert.equal(compactBlockId("opaque-block"), "opaque-block");
  assert.equal(compactBlockId(""), "Unavailable");
  assert.equal(
    blockReferenceLabel("DRAFT AIV/b-0040"),
    "Source block ID DRAFT AIV/b-0040",
  );
});

test("uses source-passage language for one and many references", () => {
  assert.equal(sourcePassageAriaLabel(1), "View 1 source passage");
  assert.equal(sourcePassageAriaLabel(3), "View 3 source passages");
});
