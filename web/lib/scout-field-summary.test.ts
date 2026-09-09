import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { loadComponent } from "../test-support/load-component.ts";

function render(overrides = {}) {
  const { ScoutFieldSummary } = loadComponent(fileURLToPath(new URL("../components/scout-field-summary.tsx", import.meta.url)));
  return renderToStaticMarkup(React.createElement(ScoutFieldSummary, {
    relations: { contradicts: 1, confirms: 2 }, strength: "partial",
    precedent: { precedent: "direct", outcome: "mixed" },
    targetCount: 1, comparatorCount: 4, insightCount: 6, ...overrides,
  }));
}

test("field summaries keep assessment signals separate from precedent and counts", () => {
  const html = render();
  const primary = html.match(/<div[^>]*aria-label="Assessment signals"[^>]*>([\s\S]*?)<\/div>/)?.[1] ?? "";
  const details = html.match(/<div[^>]*aria-label="Supporting details"[^>]*>([\s\S]*?)<\/div>/)?.[1] ?? "";
  assert.match(primary, /Conflicts 1/);
  assert.match(primary, /Supports 2/);
  assert.match(primary, /Partly grounded/);
  assert.doesNotMatch(primary, /precedent|Insights|Comparators/);
  for (const text of ["Direct precedent", "Mixed outcome", "Numeric targets", "Comparators", "Insights"]) assert.ok(details.includes(text), text);
});

test("absent assessments stay absent while an assessed zero insight count remains visible", () => {
  const html = render({ relations: { contradicts: 0, confirms: 0 }, strength: null, precedent: null,
    targetCount: 0, comparatorCount: 0, insightCount: 0 });
  assert.doesNotMatch(html, /Assessment signals|Conflicts|Supports|grounded|precedent|Numeric targets|Comparators/);
  assert.match(html, /Insights[^<]*<span[^>]*>0<\/span>/);
});

test("unfavorable and unknown outcomes remain explicit, independent of direct precedent", () => {
  for (const [outcome, label] of [["unfavorable", "Unfavorable outcome"], ["unknown", "Outcome unknown"]]) {
    const html = render({ precedent: { precedent: "direct", outcome } });
    assert.match(html, /Direct precedent/);
    assert.ok(html.includes(label));
  }
});

test("precedent assessments carry dots together while inventory counts remain unmarked", () => {
  const html = render();
  const precedent = html.split('aria-label="Precedent assessment"')[1]?.split('aria-label="Inventory counts"')[0] ?? "";
  assert.match(precedent, /Direct precedent/);
  assert.match(precedent, /Mixed outcome/);
  assert.equal((precedent.match(/aria-hidden="true"/g) ?? []).length, 2);
  const counts = html.split('aria-label="Inventory counts"')[1] ?? "";
  assert.match(counts, /Numeric targets/);
  assert.match(counts, /Insights/);
  assert.doesNotMatch(counts, /aria-hidden="true"/);
});
