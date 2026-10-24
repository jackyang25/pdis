import assert from "node:assert/strict";
import test from "node:test";

import { countLabel } from "./count-label.ts";

test("a count agrees its noun with the number, including zero", () => {
  assert.equal(countLabel(1, "source"), "1 source");
  assert.equal(countLabel(0, "source"), "0 sources");
  assert.equal(countLabel(3, "search", "searches"), "3 searches");
});
