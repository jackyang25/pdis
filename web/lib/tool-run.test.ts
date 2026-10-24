/**
 * One way to run, continue and import, shared by every tool page.
 *
 * The handlers were copied across six pages and drifted: only Scout asked about the run
 * limit before running, so on the other five a run at the limit took its minutes and was
 * then refused; Searcher cleared the selection first, so a refused search left nothing
 * on screen at all.
 */

import assert from "node:assert/strict";
import test from "node:test";

import {
  IMPORT_LIMIT_MESSAGE,
  MAX_RESULTS_PER_TOOL,
  RESULT_LIMIT_MESSAGE,
  useChunkerSession,
} from "./session.ts";
import { importTool, runTool, trackTool } from "./tool-run.ts";

type Parsed = { doc_id: string; blocks: [] };
const parsed = (doc_id: string): Parsed => ({ doc_id, blocks: [] });

function fresh() {
  useChunkerSession.getState().reset();
  return useChunkerSession.getState;
}

test("a run at the limit is refused before it starts, in the store's words", async () => {
  const get = fresh();
  for (let index = 0; index < MAX_RESULTS_PER_TOOL; index += 1) get().addResult(parsed(`run-${index}`));
  const viewed = get().selectedId;
  let started = false;

  await runTool(useChunkerSession, async () => {
    started = true;
    return parsed("one too many");
  });

  assert.equal(started, false);
  assert.equal(get().error, RESULT_LIMIT_MESSAGE);
  assert.equal(get().busy, false);
  // The run on screen stays on screen.
  assert.equal(get().selectedId, viewed);
});

test("a run reports its stages, keeps its result and clears its busy state", async () => {
  const get = fresh();
  get().setError("an earlier failure");
  const seen: (string | null)[] = [];

  await runTool(useChunkerSession, async (report) => {
    assert.equal(get().busy, true);
    assert.equal(get().error, null);
    report("parse", { completed: 1, total: 2 });
    seen.push(get().stage);
    assert.deepEqual(get().progress, { completed: 1, total: 2 });
    return parsed("done");
  });

  assert.deepEqual(seen, ["parse"]);
  assert.equal(get().busy, false);
  assert.equal(get().result?.doc_id, "done");
});

test("a failed run says why and keeps what was being viewed", async () => {
  const get = fresh();
  get().addResult(parsed("held"));

  await runTool(useChunkerSession, async () => {
    throw new Error("the service is unavailable");
  });

  assert.equal(get().error, "the service is unavailable");
  assert.equal(get().busy, false);
  assert.equal(get().result?.doc_id, "held");
});

test("tracking an in-place step returns its result without adding a run", async () => {
  const get = fresh();
  for (let index = 0; index < MAX_RESULTS_PER_TOOL; index += 1) get().addResult(parsed(`run-${index}`));
  // A continuation edits the run it continues, so the limit does not apply to it.
  const next = await trackTool(useChunkerSession, async () => parsed("continued"));
  assert.equal(next?.doc_id, "continued");
  assert.equal(get().results.length, MAX_RESULTS_PER_TOOL);
  assert.equal(get().error, null);

  const failed = await trackTool(useChunkerSession, async () => {
    throw new Error("stopped");
  });
  assert.equal(failed, null);
  assert.equal(get().error, "stopped");
});

test("an import reads the file, keeps its identity and refuses in import's words", async () => {
  const get = fresh();
  const file = (value: unknown) => ({ text: async () => JSON.stringify(value) }) as File;

  await importTool(useChunkerSession, file({ id: "saved", created_at: "2026-01-01T00:00:00.000Z", doc_id: "a" }),
    (raw) => parsed((raw as Parsed).doc_id));
  assert.equal(get().selectedId, "saved");
  assert.equal(get().results[0].created_at, "2026-01-01T00:00:00.000Z");

  await importTool(useChunkerSession, file({}), () => {
    throw new Error("not a chunker result file");
  });
  assert.equal(get().error, "Could not import result: not a chunker result file");

  for (let index = 1; index < MAX_RESULTS_PER_TOOL; index += 1) get().addResult(parsed(`run-${index}`));
  await importTool(useChunkerSession, file({ doc_id: "b" }), (raw) => parsed((raw as Parsed).doc_id));
  assert.equal(get().error, IMPORT_LIMIT_MESSAGE);
});
