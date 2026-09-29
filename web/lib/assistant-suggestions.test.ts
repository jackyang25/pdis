import assert from "node:assert/strict";
import test from "node:test";
import { openers } from "./assistant-suggestions.ts";

test("every state offers exactly two questions", () => {
  for (const state of [
    { attachments: 0, results: 0 }, { attachments: 0, results: 1 }, { attachments: 0, results: 3 },
    { attachments: 2, results: 0 }, { attachments: 2, results: 2 }, { reviewPhase: "target_review", attachments: 0, results: 1 },
  ]) {
    const pair = openers(state);
    assert.equal(pair.length, 2);
    for (const opener of pair) assert.match(opener, /[?.]$/);
  }
});

test("an empty workspace asks about the tools, not a result", () => {
  assert.deepEqual(openers({ attachments: 0, results: 0 }), ["Which tool should I use?", "What skills can you use here?"]);
});
