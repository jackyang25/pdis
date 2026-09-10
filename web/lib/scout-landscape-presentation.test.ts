import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { loadComponent } from "../test-support/load-component.ts";

const { DevelopmentLandscape, SourceList } = loadComponent(
  fileURLToPath(new URL("../app/scout/page.tsx", import.meta.url)), {}, ["DevelopmentLandscape", "SourceList"],
);
const findings = Array.from({ length: 6 }, (_, i) => ({ url: `https://example.org/${i}`, title: `Retained source ${i}`, source: "pubmed", published_at: null }));
test("Landscape keeps field lineage reachable in a disclosure without repeating its relationship badge", () => {
  const html = renderToStaticMarkup(React.createElement(DevelopmentLandscape, { programs: [{
    projection_id: "program-1", name: "Candidate", sponsors: ["A sponsor"], phases: ["Phase 3", "phase 3"], statuses: ["Recruiting"],
    record_types: ["trial_registry"], target_relationship: "direct", source_role: "experimental",
    target_relationship_reason: "Retained assessment", attribute_refs: ["first_field", "last_field"], supporting_findings: findings,
  }] }));
  const summaries = html.match(/<summary\b[^>]*>[\s\S]*?<\/summary>/g) ?? [];
  assert.ok(summaries.some((summary) => summary.includes("Retrieved for")));
  assert.match(html, /First Field/);
  assert.match(html, /Last Field/);
  assert.equal((html.match(/Direct to uploaded product/g) ?? []).length, 1);
  assert.match(html, /Experimental arm/);
  assert.match(html, /Phase 3 · phase 3/);
});

test("source list exposes its collapsed state and preserves source URLs and order", () => {
  const html = renderToStaticMarkup(React.createElement(SourceList, { findings }));
  assert.match(html, /aria-expanded="false"/);
  assert.match(html, /href="https:\/\/example.org\/0"/);
  assert.match(html, /Retained source 4/);
  assert.doesNotMatch(html, /Retained source 5/);
  assert.ok(html.indexOf("Retained source 0") < html.indexOf("Retained source 4"));
});
