import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { loadComponent } from "../test-support/load-component.ts";
import type { GateReview, QuestionAssessment } from "./api.ts";

function render(state: QuestionAssessment["state"]) {
  const cited = state === "answered" || state === "partly_answered";
  const review: GateReview = {
    org: "bmgf", intervention_class: "drug", indication: "malaria",
    gate_id: "pcd", gate_label: "Preclinical Candidate Development", bank_source: "Test bank",
    documents: [{ doc_id: "profile" }],
    blocks: [{ id: "profile:1", doc_id: "profile", ordinal: 1, block_type: "paragraph",
      content: "Retained evidence", heading_stack: [], section_label: null, structural_meta: {}, style_hint: {} }],
    disciplines: [{ id: "pds", label: "Product Development Strategy", questions: [{
      id: "PDS.1", text: "Does the candidate meet the target?", state, requirement: "required",
      statement: "Assessment statement", missing: state === "partly_answered" ? "The duration is not stated." : "",
      cited_block_ids: cited ? ["profile:1"] : [],
    }] }],
  };
  const { default: Page } = loadComponent(fileURLToPath(new URL("../app/screener/page.tsx", import.meta.url)), {
    "@/lib/session": { useScreenerSession: () => ({ result: { review }, results: [], selectedId: null }) },
    "@/lib/store": { useHeaderStore: (select: (value: unknown) => unknown) => select({ header: {} }), isContextComplete: () => false },
  });
  return renderToStaticMarkup(React.createElement(Page));
}

for (const state of ["answered", "partly_answered"] as const) {
  test(`${state} rows expose retained source passages without expanding the question`, () => {
    const html = render(state);
    assert.match(html, /In document/);
    assert.match(html, /Assessment statement/);
    if (state === "partly_answered") assert.match(html, /The duration is not stated/);
  });
}

for (const state of ["not_found", "not_applicable"] as const) {
  test(`${state} rows do not offer invented source passages`, () => {
    assert.doesNotMatch(render(state), /In document/);
  });
}

test("question text is readable content rather than a no-op disclosure", () => {
  const html = render("partly_answered");
  const buttons = html.match(/<button\b[^>]*>[\s\S]*?<\/button>/g) ?? [];
  assert.ok(!buttons.some(button => button.includes("Does the candidate meet the target?")));
  assert.doesNotMatch(html, /line-clamp-2/);
  assert.match(html, /Does the candidate meet the target\?/);
});

test("state counts accompany their heading rather than floating beside the disclosure action", () => {
  assert.match(render("partly_answered"), /<h2[^>]*>Partly answered\s*<span[^>]*> 1<\/span><\/h2>/);
});

test("a shared card retains an explicit zero count without adding a count to uncounted cards", () => {
  const { CollapsibleCard } = loadComponent(fileURLToPath(new URL("../components/collapsible-card.tsx", import.meta.url)));
  const zero = renderToStaticMarkup(React.createElement(CollapsibleCard, { title: "Findings", count: 0 }, "Body"));
  assert.match(zero, /<h2[^>]*>Findings\s*<span[^>]*> 0<\/span><\/h2>/);
  const uncounted = renderToStaticMarkup(React.createElement(CollapsibleCard, { title: "Document" }, "Body"));
  assert.match(uncounted, /<h2[^>]*>Document<\/h2>/);
  assert.match(uncounted, /aria-label="Collapse Document"/);
});

test("Screener shares its introduction and avoids repeated ordering notes", () => {
  const page = readFileSync(new URL("../app/screener/page.tsx", import.meta.url), "utf8");
  assert.match(page, /description=\{toolAuthority\("screener"\)\}/);
  assert.equal(page.match(/orderNote=\{SCREENER_ORDER_NOTE\}/g)?.length, 1);
  const partial = page.split('title="Partly answered"')[1].split("/>")[0];
  assert.doesNotMatch(partial, /defaultOpen/);
  assert.match(page, /defaultOpen=\{defaultOpen \|\| Boolean\(query\)\}/);
});

test("Screener coverage retains full discipline labels and every question", () => {
  const { ScreenerCoverageStrip } = loadComponent(fileURLToPath(new URL("../components/screener-coverage-strip.tsx", import.meta.url)));
  const label = "Chemistry, Manufacturing and Controls";
  const html = renderToStaticMarkup(React.createElement(ScreenerCoverageStrip, {
    review: { disciplines: [{ id: "cmc", label, questions: [
      { id: "q-1", state: "answered", statement: "Evidence found", cited_block_ids: ["b-1"] },
      { id: "q-2", state: "not_found", statement: "Not supplied", cited_block_ids: [] },
    ] }] }, onSelect: () => {},
  }));
  assert.match(html, new RegExp(label));
  assert.doesNotMatch(html, /truncate/);
  assert.match(html, /<ul class="grid auto-rows-fr gap-y-1"/);
  assert.match(html, /q-1/);
  assert.match(html, /q-2/);
  assert.equal((html.match(/<button/g) ?? []).length, 1);
});
