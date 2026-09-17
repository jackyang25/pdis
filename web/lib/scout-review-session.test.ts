import assert from "node:assert/strict";
import test from "node:test";
import { useScoutReviewSession } from "./scout-review-session.ts";

test("review lifecycle requires explicit finalization after decisions and corrections", () => {
  const store = useScoutReviewSession;
  store.getState().reset();
  store.getState().initialize(true);
  assert.equal(store.getState().status, "reviewing");

  store.getState().recordDecision(false);
  assert.equal(store.getState().status, "ready");
  store.getState().recordDecision(true);
  assert.equal(store.getState().status, "reviewing");
  store.getState().recordDecision(false);
  store.getState().finalize();
  assert.equal(store.getState().status, "final");
});

test("a run without review candidates is final immediately", () => {
  const store = useScoutReviewSession;
  store.getState().reset();
  store.getState().initialize(false);
  assert.equal(store.getState().status, "final");
});
