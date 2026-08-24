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
  // Leads with the visible label, per WCAG 2.5.3: the button reads "In document", so voice
  // control has to be able to ask for that.
  assert.equal(sourcePassageAriaLabel(1), "In document: 1 source passage");
  assert.equal(sourcePassageAriaLabel(3), "In document: 3 source passages");
});
