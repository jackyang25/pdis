/**
 * The card meta row answers one question: can I run this before my next meeting?
 *
 * That only works if every card answers it the same way. The field is a free
 * string, so nothing structural stops the next tool from adding a fourth shape —
 * it already held ranges, bare numbers, and "On demand" at once, and a reader
 * comparing two cards could not tell whether "2 min" and "3–5 min" were measured
 * the same way.
 */

import assert from "node:assert/strict";
import test from "node:test";

import { WORKSPACE_TOOLS } from "./tools.ts";

/** Approximate minutes, rounded to what a reader should budget. */
const DURATION = /^~\d+ min$/;

test("every available workspace tool states how long a run takes", () => {
  const available = WORKSPACE_TOOLS.filter((tool) => tool.availability === "available");
  assert.ok(available.length > 0, "no available workspace tools were found");
  for (const tool of available) {
    assert.match(
      tool.activity ?? "",
      DURATION,
      `${tool.id} publishes "${tool.activity}", which a reader cannot compare with `
        + `"~5 min". Estimates are approximate minutes, so they read as one scale.`,
    );
  }
});

test("a tool that is not built yet claims no runtime", () => {
  // Not a gap to fill: there is nothing to have timed. Publishing a number for
  // unbuilt work would be the only unmeasured figure on the page.
  for (const tool of WORKSPACE_TOOLS) {
    if (tool.availability === "available") continue;
    assert.equal(
      tool.activity,
      undefined,
      `${tool.id} is ${tool.availability} but publishes a runtime`,
    );
  }
});

test("the estimate is a budget, so it rounds up rather than to the middle", () => {
  // Pinned by example: a reader who set aside the stated time and waited longer
  // is worse served than one who finished early, so these came from observed
  // upper ends rather than averages.
  const scout = WORKSPACE_TOOLS.find((tool) => tool.id === "scout");
  assert.equal(scout?.activity, "~15 min");
});
