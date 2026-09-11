import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { loadComponent } from "../test-support/load-component.ts";
import { VERDICTS, type RequirementSnapshot, type RubricSnapshot, type SectionAssessment } from "./api.ts";

const { InspectorRequirement, InspectorRubricDetails } = loadComponent(
  fileURLToPath(new URL("../components/inspector-rubric-details.tsx", import.meta.url)),
);
const rubric: RubricSnapshot = {
  id: "pdid", display_name: "PDID template: IPDP", revision: "1.0", updated_on: "2025-04-03",
  authority: "PDID", scope: "Document review", mirrors: "The source template's full structural description",
  reference_url: "https://example.org/library", sources: [], requirements: [],
  evidence_scope: "mapped_section", stage_guidance: "Strategic planning depth.",
};
const requirement: RequirementSnapshot = {
  id: "objectives", description: "Describe development objectives.",
  expectations: "State the intended outcome.", source_refs: [],
  section_name: "Development plan", variable_name: "Objectives",
};

test("rubric details distinguish the saved rubric date from the source revision", () => {
  const html = renderToStaticMarkup(React.createElement(InspectorRubricDetails, {
    rubric: { ...rubric, sources: [{ id: "source", title: "Guideline", revision: "2021", url: "https://example.org" }] },
  }));
  assert.match(html, /Rubric updated/);
  assert.match(html, /2025-04-03/);
  assert.match(html, /2021/);
});

test("section headers use dots for single, multiple and clear verdicts without repeating absence", () => {
  const { SectionCard } = loadComponent(fileURLToPath(new URL("../app/inspector/page.tsx", import.meta.url)), {}, ["SectionCard"]);
  for (const verdict of ["not_present", "insufficient", "specified"] as const) {
    for (const variableNames of [[null], ["Schedule", "Duration"]]) {
      const section: SectionAssessment = {
        section_name: "Introduction", is_present: false, mapped_block_ids: [],
        units: variableNames.map((variable_name, rank) => ({
          id: `intro-${rank}`, section_name: "Introduction", variable_name,
          verdict, optional: verdict === "specified", statement: "", cited_block_ids: [], rank,
        })),
        verdict_counts: Object.fromEntries(VERDICTS.map(value => [value, value === verdict ? variableNames.length : 0])) as SectionAssessment["verdict_counts"],
      };
      const html = renderToStaticMarkup(React.createElement(SectionCard, { rubric, section }));
      const header = html.match(/<header\b[\s\S]*?<\/header>/)?.[0] ?? "";
      assert.match(header, /h-1\.5 w-1\.5/);
      assert.doesNotMatch(header, /Section not found in the document/);
      assert.match(html, /Section not found in the document/);
    }
  }
});

test("priority summaries retain all model text and do not truncate the worklist silently", () => {
  const { PriorityPanel } = loadComponent(fileURLToPath(new URL("../components/ui/priority-panel.tsx", import.meta.url)));
  const digest = "The opening finding. ".repeat(40) + "The final qualification must remain reachable.";
  const html = renderToStaticMarkup(React.createElement(PriorityPanel, {
    attribution: "by Inspector", defaultOpen: true, digest, emptyMessage: "No findings", orderNote: "Authored order",
    items: Array.from({ length: 12 }, (_, i) => ({ id: `item-${i}`, label: `Finding ${i}`, statement: "A finding" })),
  }));
  assert.match(html, /The final qualification must remain reachable/);
  assert.match(html, /Show all/);
  assert.match(html, /Finding 0/);
  assert.doesNotMatch(html, /Finding 11/);
});

test("template requirements retain a source link without repeating rubric-level prose", () => {
  const html = renderToStaticMarkup(React.createElement(InspectorRequirement, { rubric, requirement }));
  assert.match(html, /Describe development objectives/);
  assert.match(html, /State the intended outcome/);
  assert.match(html, /href="https:\/\/example.org\/library"/);
  assert.match(html, /Template basis/);
  assert.doesNotMatch(html, /full structural description/);
  const about = renderToStaticMarkup(React.createElement(InspectorRubricDetails, { rubric }));
  assert.match(about, /full structural description/);
});

test("guideline requirements keep their exact saved sources, not the template fallback", () => {
  const html = renderToStaticMarkup(React.createElement(InspectorRequirement, {
    rubric: { ...rubric, sources: [
      { id: "e8", title: "ICH E8 — Section 4.3", url: "https://example.org/e8", revision: "2021" },
      { id: "other", title: "Unrelated source", url: "https://example.org/other", revision: "2020" },
    ] },
    requirement: { ...requirement, source_refs: ["e8"] },
  }));
  assert.match(html, /ICH E8 — Section 4.3/);
  assert.match(html, /2021/);
  assert.doesNotMatch(html, /Template basis|Unrelated source/);
});

test("rubric information preserves the saved authority even when precise sources exist", () => {
  const html = renderToStaticMarkup(React.createElement(InspectorRubricDetails, {
    rubric: { ...rubric, mirrors: null, authority: "PDIS-authored adaptation; not endorsed by ICH.",
      sources: [{ id: "e8", title: "ICH E8", url: "https://example.org/e8", revision: "2021" }] },
  }));
  assert.match(html, /PDIS-authored adaptation; not endorsed by ICH/);
  assert.match(html, /ICH E8/);
});

test("legacy template metadata without a URL remains identifiable without inventing a link", () => {
  const html = renderToStaticMarkup(React.createElement(InspectorRequirement, {
    rubric: { ...rubric, reference_url: null }, requirement,
  }));
  assert.match(html, /PDID template: IPDP/);
  assert.doesNotMatch(html, /href=|full structural description/);
});
