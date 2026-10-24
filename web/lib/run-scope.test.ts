/**
 * A run's scope line: what was examined, and under which publication window.
 */

import assert from "node:assert/strict";
import test from "node:test";

import { runScope } from "./result-file.ts";

const scout = { blocks: [{ doc_id: "RSV Maternal Vaccine iTPP" }], indication: "respiratory_syncytial_virus", intervention_class: "vaccine", source_type: "itpp" };

test("a Scout run's publication window is part of its scope, and absent when none was set", () => {
  assert.equal(runScope(scout, "scout"), "Respiratory Syncytial Virus · Vaccine · iTPP");
  // The window removes evidence before anything is counted, so it is scope, not a caveat.
  assert.equal(
    runScope({ ...scout, published_since: "2024-03-01" }, "scout"),
    "Respiratory Syncytial Virus · Vaccine · iTPP · evidence since March 1, 2024",
  );
});
