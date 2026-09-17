import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { loadComponent } from "../test-support/load-component.ts";

const { RunPanel } = loadComponent(fileURLToPath(new URL("../components/run-panel.tsx", import.meta.url)));

test("a remounted run panel shows elapsed time from the run, not the mount", (t) => {
  const clock = t.mock.method(Date, "now", () => 61000);
  const props = { busy: true, startedAt: 1000, steps: [{ key: "parse", label: "Parsing" }], currentStage: "parse", onRun: () => {} };
  assert.match(renderToStaticMarkup(React.createElement(RunPanel, props)), /1:00/);
  clock.mock.mockImplementation(() => 121000);
  assert.match(renderToStaticMarkup(React.createElement(RunPanel, props)), /2:00/);
});
