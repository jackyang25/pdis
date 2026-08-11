/**
 * A tool keeps its finished runs for the session, and reviewing one is not a
 * new run.
 *
 * The store previously held exactly one result, so a second run replaced the
 * first and the only way back was to re-import a file. These pin the two things
 * that make history safe: `setResult` still edits the run in place, because
 * review is a sequence of edits to one run, and identity survives export so a
 * file already held is never held twice.
 */

import assert from "node:assert/strict";
import test from "node:test";

import {
  MAX_RESULTS_PER_TOOL,
  RESULT_LIMIT_MESSAGE,
  useScoutSession,
} from "./session.ts";

type Scout = { doc_id: string; phase?: string };

function store() {
  useScoutSession.getState().reset();
  return useScoutSession.getState;
}

test("a finished run is kept and becomes the one being viewed", () => {
  const get = store();
  const outcome = get().addResult({ doc_id: "polio" } as never);

  assert.equal(outcome.added, true);
  assert.equal(get().results.length, 1);
  assert.equal((get().result as unknown as Scout).doc_id, "polio");
  assert.equal(get().selectedId, outcome.id);
});

test("a second run is added rather than replacing the first, newest first", () => {
  const get = store();
  get().addResult({ doc_id: "first" } as never);
  get().addResult({ doc_id: "second" } as never);

  assert.deepEqual(
    get().results.map((entry) => (entry.result as unknown as Scout).doc_id),
    ["second", "first"],
  );
  assert.equal((get().result as unknown as Scout).doc_id, "second");
});

test("reviewing edits the selected run in place", () => {
  // Scout's review calls setResult repeatedly - approving a target, finalizing
  // a phase. Each of those becoming a history entry would bury the actual runs.
  const get = store();
  get().addResult({ doc_id: "polio", phase: "target_review" } as never);

  get().setResult({ doc_id: "polio", phase: "evidence_review" } as never);
  get().setResult({ doc_id: "polio", phase: "final" } as never);

  assert.equal(get().results.length, 1);
  assert.equal((get().result as unknown as Scout).phase, "final");
  assert.equal((get().results[0].result as unknown as Scout).phase, "final");
});

test("re-importing a file already held selects it instead of duplicating it", () => {
  const get = store();
  get().addResult({ doc_id: "polio" } as never, { id: "run-a" });
  const second = get().addResult({ doc_id: "polio" } as never, { id: "run-a" });

  assert.deepEqual(second, { added: false, reason: "duplicate", id: "run-a" });
  assert.equal(get().results.length, 1);
  assert.equal(get().selectedId, "run-a");
});

test("a re-run of the same document is a different run", () => {
  // Identity is the file's, not the document's: running polio twice produces
  // two runs a user may legitimately want to compare.
  const get = store();
  get().addResult({ doc_id: "polio" } as never);
  get().addResult({ doc_id: "polio" } as never);

  assert.equal(get().results.length, 2);
});

test("at the limit a run is refused rather than the oldest dropped", () => {
  const get = store();
  for (let index = 0; index < MAX_RESULTS_PER_TOOL; index += 1) {
    assert.equal(get().addResult({ doc_id: `run-${index}` } as never).added, true);
  }
  const refused = get().addResult({ doc_id: "one-too-many" } as never);

  assert.equal(refused.added, false);
  assert.equal(refused.added === false && refused.reason, "at_limit");
  assert.equal(get().results.length, MAX_RESULTS_PER_TOOL);
  // The oldest is still there: nothing was discarded to make room.
  assert.equal(
    (get().results.at(-1)!.result as unknown as Scout).doc_id,
    "run-0",
  );
});

test("removing the viewed run falls back to another, not to nothing", () => {
  const get = store();
  get().addResult({ doc_id: "older" } as never);
  const newer = get().addResult({ doc_id: "newer" } as never);

  get().removeResult(newer.id);

  assert.equal(get().results.length, 1);
  assert.equal((get().result as unknown as Scout).doc_id, "older");
  assert.equal(get().selectedId, get().results[0].id);
});

test("selecting a run switches what every reader sees", () => {
  const get = store();
  const older = get().addResult({ doc_id: "older" } as never);
  get().addResult({ doc_id: "newer" } as never);

  get().selectResult(older.id);

  assert.equal((get().result as unknown as Scout).doc_id, "older");
});

test("each run records when it happened", () => {
  const get = store();
  get().addResult({ doc_id: "polio" } as never);

  assert.match(get().results[0].created_at, /^\d{4}-\d{2}-\d{2}T/);
});

test("a run that cannot be kept says so, without the caller having to", () => {
  // `AddResultOutcome` is a return value a page can discard, and four of six did — so a
  // fifth run on those finished, cost its time, and then silently failed to appear. The
  // store is the only thing that knows the result was dropped, so it is what reports it.
  const get = store();
  for (let index = 0; index < MAX_RESULTS_PER_TOOL; index += 1) {
    get().addResult({ doc_id: `run-${index}` } as never);
  }
  assert.equal(get().error, null);

  const refused = get().addResult({ doc_id: "one too many" } as never);
  assert.equal(refused.added, false);
  assert.equal(get().results.length, MAX_RESULTS_PER_TOOL);
  assert.equal(get().error, RESULT_LIMIT_MESSAGE);
  // The run being viewed is untouched: a refusal must not also change what is on screen.
  assert.equal((get().result as unknown as Scout).doc_id, "run-4");
});

test("re-importing a file already held is not an error", () => {
  // It selects the run instead. Reporting that as a failure would tell a reader
  // something went wrong when the file they wanted is now open.
  const get = store();
  const first = get().addResult({ doc_id: "held" } as never, { id: "fixed" });
  get().addResult({ doc_id: "other" } as never);

  const again = get().addResult({ doc_id: "held" } as never, { id: "fixed" });
  assert.equal(again.added, false);
  assert.equal(get().error, null);
  assert.equal(get().selectedId, first.id);
});
