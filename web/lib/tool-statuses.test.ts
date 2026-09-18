import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { loadComponent } from "../test-support/load-component.ts";

const path = fileURLToPath(new URL("./use-tool-statuses.ts", import.meta.url));
const { toolStatus } = loadComponent(path);

test("queue and active work take priority over reviews and earlier results", () => {
  const state = { busy: true, stage: "queued", results: [{}] };
  assert.equal(toolStatus(state, true), "Waiting for capacity");
  state.stage = "parse";
  assert.equal(toolStatus(state, true), "Running");
  state.busy = false;
  assert.equal(toolStatus(state, true), "Ready for review");
  assert.equal(toolStatus(state), "Results available");
  state.results = [];
  assert.equal(toolStatus(state), null);
});

test("starting a run is running even before its first stage arrives", () => {
  assert.equal(toolStatus({ busy: true, stage: null, results: [] }), "Running");
});

test("all session-backed tools are connected, with both Scout review checkpoints", () => {
  const state = { busy: false, stage: null, results: [{}], result: { phase: "target_review" } };
  const hooks = Object.fromEntries(["Inspector", "Aligner", "Screener", "Scout", "Chunker", "Searcher"]
    .map(tool => [`use${tool}Session`, (select: (state: unknown) => unknown) => select(state)]));
  const { useToolStatuses } = loadComponent(path, { "@/lib/session": hooks });
  for (const phase of ["target_review", "evidence_review", "final"]) {
    state.result.phase = phase;
    const statuses = useToolStatuses();
    assert.equal(statuses.scout, phase === "final" ? "Results available" : "Ready for review");
    for (const tool of ["inspector", "aligner", "screener", "chunker", "searcher"]) {
      assert.equal(statuses[tool], "Results available");
    }
    assert.equal(statuses.archivist, undefined);
  }
});
