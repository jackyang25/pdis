import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { loadComponent } from "../test-support/load-component.ts";

const WEB = path.resolve(import.meta.dirname, "..");
const { SegmentedControl } = loadComponent(
  fileURLToPath(new URL("../components/ui/segmented-control.tsx", import.meta.url)),
);

test("a segmented control presses exactly the chosen option", () => {
  const html = renderToStaticMarkup(React.createElement(SegmentedControl, {
    options: [{ value: "a", label: "A" }, { value: "b", label: "B" }, { value: "c", label: "C" }],
    value: "b",
    onChange: () => {},
    "aria-label": "Choose one",
  }));
  assert.match(html, /^<div role="group" aria-label="Choose one"/);
  assert.equal((html.match(/aria-pressed="true"/g) ?? []).length, 1);
  assert.equal((html.match(/aria-pressed="false"/g) ?? []).length, 2);
  assert.match(html, /aria-pressed="true"[^>]*>B</);
});

// Surfaces that choose one view among a few - the docs page's diagram, and once the Tools
// page's audience - were two looks for one control: a segmented track in one, separate
// buttons with the chosen one filled dark in the other. One component, so another cannot
// arrive as another look.
test("every one-of-a-few view switch is the shared segmented control", () => {
  for (const file of ["components/docs/architecture-graph.tsx"]) {
    const source = readFileSync(path.join(WEB, file), "utf8");
    assert.match(source, /<SegmentedControl\b/, `${file} no longer uses the shared control`);
    assert.doesNotMatch(source, /aria-pressed=/, `${file} builds its own pressed buttons again`);
  }
});
