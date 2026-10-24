import assert from "node:assert/strict";
import test from "node:test";

import { usePriorityReadingStore } from "./priority-reading.ts";
import { useInspectorSession } from "./session.ts";

test("a removed run's readings go with it, and other runs keep theirs", async () => {
  const session = useInspectorSession.getState;
  session().reset();
  const kept = session().addResult({} as never, { id: "kept" });
  const removed = session().addResult({} as never, { id: "removed" });
  const reading = async () => ({ summary: "", points: [] }) as never;
  // Inspector keys a reading per rubric, under the run's id.
  for (const key of [kept.id, `${removed.id}:who`, removed.id]) usePriorityReadingStore.getState().read(key, reading);
  await new Promise((resolve) => setTimeout(resolve, 0));

  session().removeResult(removed.id);
  assert.deepEqual(Object.keys(usePriorityReadingStore.getState().entries), [kept.id]);

  session().reset();
  assert.deepEqual(usePriorityReadingStore.getState().entries, {});
});

test("a reading that arrives after its run was removed does not come back", async () => {
  const session = useInspectorSession.getState;
  session().reset();
  const run = session().addResult({} as never, { id: "late" });
  let arrive: (value: never) => void = () => {};
  usePriorityReadingStore.getState().read(run.id, () => new Promise((resolve) => { arrive = resolve; }));
  session().removeResult(run.id);
  arrive({ summary: "", points: [] } as never);
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.deepEqual(usePriorityReadingStore.getState().entries, {});
});
