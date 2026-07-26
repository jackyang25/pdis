import assert from "node:assert/strict";
import test from "node:test";
import type { Conformity } from "./api.ts";
import { useScoutReviewSession } from "./scout-review-session.ts";

test("review lifecycle requires explicit finalization and supports undo", () => {
  const store = useScoutReviewSession;
  store.getState().reset();
  store.getState().initialize(true);
  assert.equal(store.getState().status, "reviewing");

  const previousScore = {} as Conformity;
  store.getState().recordDecision({
    decision: "approve",
    previousConformity: [previousScore],
  }, false);
  assert.equal(store.getState().status, "ready");
  assert.equal(store.getState().history.length, 1);

  const undone = store.getState().undoLast();
  assert.equal(undone?.previousConformity[0], previousScore);
  assert.equal(store.getState().status, "reviewing");
  assert.equal(store.getState().history.length, 0);

  store.getState().recordDecision({
    decision: "reject",
    previousConformity: [previousScore],
  }, false);
  store.getState().finalize();
  assert.equal(store.getState().status, "final");
  assert.equal(store.getState().history.length, 0);
});

test("a run without review candidates is final immediately", () => {
  const store = useScoutReviewSession;
  store.getState().reset();
  store.getState().initialize(false);
  assert.equal(store.getState().status, "final");
});
