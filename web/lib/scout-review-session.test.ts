import assert from "node:assert/strict";
import test from "node:test";
import type { ScoutResponse } from "./api.ts";
import { continueScout } from "./api.ts";
import { targetReviewFixture } from "../test-support/scout-review-fixture.ts";
import { scoutReviewStatus } from "./scout-review-session.ts";

function scout(phase: ScoutResponse["phase"], pendingEvidence = 0): ScoutResponse {
  return {
    phase,
    quantitative_ledger: { targets: [], reviews: [] },
    conformity: [{
      target_id: "t1",
      measurements: Array.from({ length: pendingEvidence }, () => ({ admission_status: "needs_review" })),
      excluded_measurements: [],
    }],
  } as unknown as ScoutResponse;
}

test("review lifecycle requires explicit finalization after decisions and corrections", () => {
  assert.equal(scoutReviewStatus(scout("evidence_review", 2)), "reviewing");
  // Every candidate decided is ready, not final: finalizing is its own act.
  assert.equal(scoutReviewStatus(scout("evidence_review", 0)), "ready");
  assert.equal(scoutReviewStatus(scout("final")), "final");
});

test("a run still choosing its targets has no evidence review yet", () => {
  assert.equal(scoutReviewStatus(scout("target_review")), "targets");
});

test("each run answers for itself, so switching runs cannot strand one in another's state", () => {
  // One status used to be held for the whole tool. A run paused at evidence review,
  // then a final run, then selecting the paused run again rendered nothing at all,
  // because the held status still said "final".
  const paused = scout("evidence_review", 1);
  const finished = scout("final");
  assert.equal(scoutReviewStatus(finished), "final");
  assert.equal(scoutReviewStatus(paused), "reviewing");
});

test("the draft a continuation sends keeps the retrieval scope it was reviewed under", async (t) => {
  // The continuation searches the scope the reviewer saw and does not read it again, so
  // the API refuses a draft without it (422). Anything that rebuilt the draft from the
  // fields it knew would drop it.
  const draft = targetReviewFixture("completed");
  assert.ok(draft.retrieval_scope.entries.length > 0);
  let sent: { draft: ScoutResponse } | undefined;
  t.mock.method(globalThis, "fetch", async (_url: string, init: RequestInit) => {
    sent = JSON.parse(String(init.body));
    return new Response(`${JSON.stringify({ event: "complete", result: { ...draft, phase: "final" } })}\n`);
  });
  await continueScout(draft);
  assert.deepEqual(sent?.draft.retrieval_scope, draft.retrieval_scope);
  assert.deepEqual(sent?.draft.reconciliations, draft.reconciliations);
  assert.deepEqual(sent?.draft, draft);
});
