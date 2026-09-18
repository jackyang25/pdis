import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { loadComponent } from "../test-support/load-component.ts";

const { ConsistencyView } = loadComponent(
  fileURLToPath(new URL("../app/inspector/page.tsx", import.meta.url)), {}, ["ConsistencyView"],
);
const { InterfaceNote } = loadComponent(
  fileURLToPath(new URL("../components/ui/evidence-text.tsx", import.meta.url)),
);
const finding = { id: "conflict", section_name: null, variable_name: null,
  verdict: "section_conflict", statement: "Two dates disagree.", optional: false,
  cited_block_ids: [], rank: 0 };

test("consistency coverage uses the shared notice presentation without a second row inset", () => {
  const html = renderToStaticMarkup(React.createElement(ConsistencyView, {
    findings: [finding], status: "partial",
  }));
  const note = renderToStaticMarkup(React.createElement(InterfaceNote, { className: "mb-3" },
    "The document exceeded the full-pass context bound; findings reflect the retained section-balanced context."));
  assert.ok(html.includes(note));
  assert.match(html, /Two dates disagree\./);
  assert.match(html, /Section conflict/);
});

test("an incomplete empty check does not claim the document has no conflicts", () => {
  const html = renderToStaticMarkup(React.createElement(ConsistencyView, {
    findings: [], status: "partial",
  }));
  assert.match(html, /Consistency coverage is incomplete/);
  assert.doesNotMatch(html, /No cross-section conflicts identified/);
});
