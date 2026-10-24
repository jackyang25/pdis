import type { StageProgress } from "./api";
import { readResultIdentity } from "./result-file.ts";
import type { ToolSessionStore } from "./session.ts";

/** What a tool's request calls as its stream reports a stage. */
export type StageReporter = (stage: string, progress?: StageProgress) => void;

/**
 * Run a step that occupies the tool - busy, staged, its failure reported - and return
 * what it produced, or null when it failed.
 *
 * The part of a run that is not about keeping it, so Scout's continuation, which edits
 * the run it continues, shares it with every new run.
 */
export async function trackTool<TResult, TOutput = TResult>(
  store: ToolSessionStore<TResult>,
  task: (report: StageReporter) => Promise<TOutput>,
): Promise<TOutput | null> {
  const session = store.getState();
  session.setBusy(true);
  session.setError(null);
  session.setStage(null);
  session.setProgress(null);
  const report: StageReporter = (stage, progress) => {
    store.getState().setStage(stage);
    store.getState().setProgress(progress ?? null);
  };
  try {
    return await task(report);
  } catch (error) {
    store.getState().setError((error as Error).message);
    return null;
  } finally {
    store.getState().setBusy(false);
  }
}

/**
 * Start a new run and keep its result.
 *
 * Asks the store first, because a run at the limit would otherwise spend its minutes and
 * only then be refused. The refusal is the store's message either way, and nothing on
 * screen is cleared before the run is known to be kept.
 */
export async function runTool<TResult>(
  store: ToolSessionStore<TResult>,
  task: (report: StageReporter) => Promise<TResult>,
): Promise<void> {
  if (!store.getState().canAddResult()) return;
  const result = await trackTool(store, task);
  if (result !== null) store.getState().addResult(result);
}

/**
 * Open a saved file through the tool's own unpacker, under the identity it carries.
 *
 * A file already held is selected rather than refused, which is why the limit is the
 * store's to apply after reading rather than the page's to check before.
 */
export async function importTool<TResult>(
  store: ToolSessionStore<TResult>,
  file: File,
  unpack: (raw: unknown) => TResult,
): Promise<void> {
  store.getState().setError(null);
  try {
    const raw: unknown = JSON.parse(await file.text());
    const result = unpack(raw);
    store.getState().setStage(null);
    store.getState().setProgress(null);
    store.getState().importResult(result, readResultIdentity(raw));
  } catch (error) {
    store.getState().setError(`Could not import result: ${(error as Error).message}`);
  }
}
