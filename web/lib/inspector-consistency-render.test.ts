import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { readFileSync } from "node:fs";
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
  const note = renderToStaticMarkup(React.createElement(InterfaceNote, { className: "mx-5 mb-3 sm:mx-6" },
    "The document exceeded the full-pass context bound; findings reflect the retained section-balanced context."));
  assert.ok(html.includes(note));
  assert.match(html, /Two dates disagree\./);
  assert.match(html, /Section conflict/);
  // The rows bring their own inset, so what holds them must not add a second one: a padded
  // wrapper once put every conflict 24px inside the rest of the card.
  const page = readFileSync(fileURLToPath(new URL("../app/inspector/page.tsx", import.meta.url)), "utf8");
  const tab = page.slice(page.indexOf('value="consistency"'), page.indexOf("<ConsistencyView"));
  assert.doesNotMatch(tab, /<div className="[^"]*\bpx-5\b[^"]*">\s*(?:\{\/\*[\s\S]*?\*\/\}\s*)?<p/);
  assert.match(tab, /<div className="py-5 sm:py-6">/);
});

test("an incomplete empty check does not claim the document has no conflicts", () => {
  const html = renderToStaticMarkup(React.createElement(ConsistencyView, {
    findings: [], status: "partial",
  }));
  assert.match(html, /Consistency coverage is incomplete/);
  assert.doesNotMatch(html, /No cross-section conflicts identified/);
});
