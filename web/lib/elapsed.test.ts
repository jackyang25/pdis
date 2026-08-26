/**
 * The one number on the progress row that is measured rather than inferred.
 *
 * The bar beside it shows stage position, which is not time — Scout's stages
 * differ by minutes, so a percentage would assert precision the run does not
 * have. Elapsed time is the honest signal that something is still moving.
 */

import assert from "node:assert/strict";
import test from "node:test";

import { formatElapsed } from "./elapsed.ts";

test("seconds are zero-padded so the number does not jump width", () => {
  assert.equal(formatElapsed(0), "0:00");
  assert.equal(formatElapsed(9_000), "0:09");
  assert.equal(formatElapsed(70_000), "1:10");
});

test("it rounds down, never claiming time that has not passed", () => {
  assert.equal(formatElapsed(1_999), "0:01");
  assert.equal(formatElapsed(59_999), "0:59");
});

test("an hour adds a field rather than counting to ninety minutes", () => {
  // Scout runs about twenty minutes; an hour means something went wrong, and "1:02:03"
  // says so more clearly than "62:03".
  assert.equal(formatElapsed(3_600_000), "1:00:00");
  assert.equal(formatElapsed(3_723_000), "1:02:03");
});

test("a clock that moved backwards reads zero, not a negative", () => {
  // Elapsed is measured from Date.now(); a system clock change must not render
  // "-1:-3" on screen.
  assert.equal(formatElapsed(-5_000), "0:00");
});
