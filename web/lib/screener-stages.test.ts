import assert from "node:assert/strict";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { loadComponent } from "../test-support/load-component.ts";

test("Screener shows evidence selection as an active step before triage", () => {
  const { STEPS } = loadComponent(fileURLToPath(new URL("../app/screener/page.tsx", import.meta.url)), {}, ["STEPS"]);
  const { ProgressSteps } = loadComponent(fileURLToPath(new URL("../components/progress-steps.tsx", import.meta.url)));
  assert.deepEqual(STEPS.map((step: { key: string }) => step.key), ["resolve", "parse", "select", "assess"]);
  const html = renderToStaticMarkup(createElement(ProgressSteps, { steps: STEPS, currentStage: "select", busy: true, startedAt: null }));
  assert.match(html, /Selecting question evidence/);
  assert.match(html, /3 of 4/);
});
