import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { loadComponent } from "../test-support/load-component.ts";

import type { DraftResult, DraftVariable } from "./api.ts";
import {
  DRAFTER_PANELS,
  countVariables,
  drafterMetricItems,
  evidenceSources,
  figureLine,
  observationFigure,
  panelVariables,
  suggestionLines,
} from "./drafter-presentation.ts";

function variable(name: string, overrides: Partial<DraftVariable> = {}): DraftVariable {
  return {
    name, label: name.split(".")[1].replaceAll("_", " "), description: "", evidence_domain: "clinical",
    status: "complete", failure: null, observations: [], statistics: [],
    suggestion: { kind: "range", minimum: "50%", preferred: "75%", statement: "", rationale: "Because.", leans_on: "comparable_products", basis_ids: [] },
    unread_findings: 0,
    unverified_quotes: 0,
    ...overrides,
  };
}

const insufficient = { kind: "insufficient" as const, minimum: "", preferred: "", statement: "", rationale: "", leans_on: "" as const, basis_ids: [] };

function draft(): DraftResult {
  return {
    org: "bmgf", source_type: "itpp", intervention_class: "vaccine", indication: "malaria", intended_use: "", display_name: "Vaccine",
    sources: [], failed_sources: [], unconfigured_sources: [], source_errors: [],
    variables: [
      variable("vaccine.efficacy"),
      variable("vaccine.dosing_schedule", { evidence_domain: "product", suggestion: { ...variable("x.y").suggestion!, kind: "statement", minimum: "", preferred: "", statement: "Three doses." } }),
      variable("vaccine.cogs", { suggestion: insufficient }),
      variable("vaccine.shelf_life", { status: "failed", suggestion: null, failure: { code: "suggestion_failed", message: "No valid reply.", cause: "invalid_model_response" } }),
    ],
  };
}

test("every variable falls in exactly one panel, in the order a reviewer works", () => {
  const result = draft();
  assert.deepEqual(DRAFTER_PANELS.map((panel) => panel.id), ["suggested", "insufficient", "failed"]);
  const placed = DRAFTER_PANELS.flatMap((panel) => panelVariables(result, panel.id, "").map((item) => item.name));
  assert.deepEqual(placed.sort(), result.variables.map((item) => item.name).sort());
  assert.deepEqual(countVariables(result), { total: 4, suggested: 2, insufficient: 1, failed: 1 });
});

test("a search narrows every panel by label and suggestion, never by text the row hides", () => {
  const result = draft();
  result.variables[0].description = "Claims about protective efficacy.";
  assert.deepEqual(panelVariables(result, "suggested", "claims about").map((item) => item.name), []);
  assert.deepEqual(panelVariables(result, "suggested", "three doses").map((item) => item.name), ["vaccine.dosing_schedule"]);
  assert.deepEqual(panelVariables(result, "suggested", "efficacy").map((item) => item.name), ["vaccine.efficacy"]);
});

test("a suggestion reads as its range or its statement", () => {
  assert.deepEqual(suggestionLines(draft().variables[0].suggestion!), ["Minimum 50%", "Preferred 75%"]);
  assert.deepEqual(suggestionLines(draft().variables[1].suggestion!), ["Three doses."]);
  assert.deepEqual(suggestionLines(insufficient), []);
});

test("figures say what they are: values stated in one unit, not one measured cohort", () => {
  assert.equal(
    figureLine({ unit: "%", observation_ids: ["a", "b", "c", "d", "e"], count: 5, minimum: 56, maximum: 77, median: 68, lower_quartile: 60, upper_quartile: 74 }),
    "5 values stated in %: median 68, middle half 60–74, range 56–77",
  );
});

// --- rendering -----------------------------------------------------------------------------

const { DrafterVariableRow } = loadComponent(fileURLToPath(new URL("../components/drafter-variable.tsx", import.meta.url)));

function withEvidence(): DraftVariable {
  return variable("vaccine.efficacy", {
    observations: [
      { id: "vaccine.efficacy:o1", basis: "comparable_product", url: "https://pubmed.org/1", title: "RTS,S phase 3",
        source_label: "PubMed", product: "RTS,S", measure: "efficacy", quote: "efficacy was 56%",
        value: { value: 56, lower: null, upper: null, unit: "%", text: "stated" }, numeric_eligible: true,
        published_at: "2021-01-01", published_precision: "year" },
      { id: "vaccine.efficacy:g1", basis: "published_guidance", url: "https://who.int/ppc", title: "Malaria vaccine PPC",
        source_label: "WHO", product: "WHO", measure: "", quote: "at least 75% efficacy", value: null, numeric_eligible: false,
        published_at: null, published_precision: "" },
    ],
    suggestion: { kind: "range", minimum: "50%", preferred: "75%", statement: "", rationale: "Comparable vaccines reached 56%; WHO prefers 75%.",
      leans_on: "both", basis_ids: ["vaccine.efficacy:o1", "vaccine.efficacy:g1"] },
  });
}

const render = (props: Record<string, unknown>) => renderToStaticMarkup(React.createElement(DrafterVariableRow, props));

test("the two kinds of evidence are listed apart, each counted", () => {
  const html = render({ variable: withEvidence() });
  assert.match(html, /Comparable products<\/span><span[^>]*>1</);
  assert.match(html, /Published guidance<\/span><span[^>]*>1</);
  assert.match(html, /Minimum 50% · Preferred 75%/);
});

test("each source names when it was published, at the precision it stated, and nothing when undated", () => {
  const html = render({ variable: withEvidence() });
  // A year-only date is never shown to the month, or it reads as a January publication.
  assert.match(html, /PubMed · 2021 · Cited by the suggestion/);
  assert.match(html, /WHO · Cited by the suggestion/);
});

test("a variable nothing spoke to says so in the tool's own words", () => {
  const html = render({ variable: variable("vaccine.cogs", { suggestion: insufficient }) });
  assert.match(html, /No source this run found spoke to this variable/);
});

test("the outcome row shows the model's readings at zero and failures only when present", () => {
  const result = draft();
  result.variables = result.variables.filter((item) => item.status !== "failed");
  const labels = drafterMetricItems(result).map((item) => `${item.label} ${item.count}`);
  assert.deepEqual(labels, ["Suggested 2", "Not enough evidence 1"]);
});

test("the no-evidence note appears only when nothing was retrieved or read", () => {
  const withObservations = variable("vaccine.cogs", { suggestion: insufficient, observations: withEvidence().observations });
  assert.doesNotMatch(render({ variable: withObservations }), /No source this run found/);
  const unread = variable("vaccine.cogs", { suggestion: insufficient, unread_findings: 2 });
  assert.doesNotMatch(render({ variable: unread }), /No source this run found/);
});

test("quotes a source does not contain are counted beside the sources set aside", () => {
  // A reader's quote that its excerpt does not hold is not kept, so it never becomes an
  // observation. Unstated, a variable that lost every quote would read as one nothing
  // spoke to.
  const html = render({ variable: variable("vaccine.cogs", { suggestion: insufficient, unread_findings: 1, unverified_quotes: 3 }) });
  assert.match(html, /1 source could not be read\s+and was set aside\./);
  assert.match(html, /3 quotes could not be found in their source\s+and were set aside\./);
  const quotesOnly = render({ variable: variable("vaccine.cogs", { suggestion: insufficient, unverified_quotes: 1 }) });
  assert.match(quotesOnly, /1 quote could not be found in its source\s+and was set aside\./);
  assert.doesNotMatch(quotesOnly, /No source this run found/);
  assert.doesNotMatch(render({ variable: withEvidence() }), /could not be found in/);
});

test("a row offers nothing to decide: it shows the suggestion and its evidence", () => {
  const html = render({ variable: withEvidence() });
  assert.doesNotMatch(html, /<button[^>]*>(Accept|Edit|Clear|Save)<\/button>/);
  assert.match(html, /Minimum 50% · Preferred 75%/);
});

test("one source is listed once however many products it names, cited sources first", () => {
  const base = withEvidence().observations[0];
  const page = { ...base, url: "https://cdc.gov/rsv", title: "RSV immunization" };
  const subject = variable("vaccine.product", {
    observations: [
      { ...base, id: "a", url: "https://pubmed.org/9", title: "Uncited trial" },
      { ...page, id: "b", product: "Arexvy" },
      { ...page, id: "c", product: "Abrysvo" },
    ],
    suggestion: { ...withEvidence().suggestion!, basis_ids: ["c"] },
  });
  const sources = evidenceSources(subject, "comparable_product");
  assert.deepEqual(sources.map((source) => [source.url, source.cited, source.passages.length]), [
    ["https://cdc.gov/rsv", true, 1],
    ["https://pubmed.org/9", false, 1],
  ]);
  // One sentence read for two products is quoted once and names both.
  assert.deepEqual(sources[0].passages[0].products, ["Arexvy", "Abrysvo"]);
  const html = render({ variable: subject });
  assert.equal(html.match(/RSV immunization/g)?.length, 1);
  assert.equal(html.match(/efficacy was 56%/g)?.length, 2);
  assert.match(html, /Comparable products<\/span><span[^>]*>2</);
});

test("an observation's figure is its value or its range, in its own unit", () => {
  assert.equal(observationFigure({ value: 56, lower: null, upper: null, unit: "%", text: "stated" }), "56%");
  assert.equal(observationFigure({ value: null, lower: 30, upper: 120, unit: "µg", text: "stated" }), "30–120 µg");
  assert.equal(observationFigure({ value: 3, lower: null, upper: null, unit: "", text: "stated" }), "3");
  assert.equal(observationFigure(null), "");
});

test("a suggestion and its rationale are one contribution, marked once", () => {
  const html = render({ variable: withEvidence() });
  assert.equal((html.match(/viewBox="0 0 24 24"[^>]*class="mr-\[0\.45em\]/g) ?? []).length, 1);
});

test("a row offers to report a problem with its suggestion", () => {
  assert.match(render({ variable: withEvidence() }), /Report a problem/);
});
