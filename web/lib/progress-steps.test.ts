import assert from "node:assert/strict";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { loadComponent } from "../test-support/load-component.ts";

const { ProgressSteps, checklistRows, MAX_LISTED_STEPS } = loadComponent(
  fileURLToPath(new URL("../components/progress-steps.tsx", import.meta.url)),
);
const steps = (count: number) => Array.from({ length: count }, (_, index) => ({ key: `s${index}`, label: `Stage ${index + 1}` }));
const describe = (rows: { kind: string; state: string; step?: { label: string }; count?: number }[]) =>
  rows.map((row) => row.kind === "step" ? `${row.state}:${row.step?.label}` : `${row.state}:+${row.count}`);

test("a short run lists every stage, ticked up to the current one", () => {
  assert.deepEqual(describe(checklistRows(steps(4), 2, false)),
    ["done:Stage 1", "done:Stage 2", "active:Stage 3", "pending:Stage 4"]);
});

test("a long run lists the stages around the current one and counts the rest", () => {
  const rows = describe(checklistRows(steps(15), 7, false));
  assert.deepEqual(rows, ["done:+6", "done:Stage 7", "active:Stage 8", "pending:Stage 9", "pending:Stage 10", "pending:+5"]);
  assert.equal(rows.filter((row) => !row.includes("+")).length, MAX_LISTED_STEPS - 1);
});

test("a long run keeps a full window at either end", () => {
  assert.deepEqual(describe(checklistRows(steps(15), 0, false)),
    ["active:Stage 1", "pending:Stage 2", "pending:Stage 3", "pending:Stage 4", "pending:+11"]);
  assert.deepEqual(describe(checklistRows(steps(15), 14, false)),
    ["done:+11", "done:Stage 12", "done:Stage 13", "done:Stage 14", "active:Stage 15"]);
});

test("a queued run claims no stage", () => {
  assert.ok(checklistRows(steps(4), 0, true).every((row: { state: string }) => row.state === "pending"));
  const html = renderToStaticMarkup(createElement(ProgressSteps, { steps: steps(4), currentStage: "queued", busy: true, startedAt: null }));
  assert.match(html, /role="status"[^>]*>Waiting for capacity</);
  assert.doesNotMatch(html, /lucide-check/);
});

test("the live region names the stage, its position and its count", () => {
  const html = renderToStaticMarkup(createElement(ProgressSteps, {
    steps: steps(4), currentStage: "s2", busy: true, startedAt: null, progress: { completed: 12, total: 54 },
  }));
  assert.match(html, /role="status"[^>]*>Stage 3, step 3 of 4, 12 of 54</);
  assert.match(html, /12\/54/);
  assert.equal((html.match(/lucide-check/g) ?? []).length, 2);
});
