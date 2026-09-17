import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { loadComponent } from "../test-support/load-component.ts";
import { TONE_TINT } from "./tone.ts";
import { reviewFixture, evidenceReviewFixture } from "../test-support/scout-review-fixture.ts";

const { ReviewListRow, ReviewActions, ReviewCheckpointHeader, ReviewEstimateChoices, defaultReviewEstimateId, QuantitativeReviewCheckpoint, DocumentTargetReviewCheckpoint } = loadComponent(
  fileURLToPath(new URL("../app/scout/page.tsx", import.meta.url)), {}, ["ReviewListRow", "ReviewActions", "ReviewCheckpointHeader", "ReviewEstimateChoices", "defaultReviewEstimateId", "QuantitativeReviewCheckpoint", "DocumentTargetReviewCheckpoint"],
);

test("qualifier details distinguish document content from every matching-rule state", () => {
  const { TargetQualifierDetails } = loadComponent(fileURLToPath(new URL("../components/scout-comparison.tsx", import.meta.url)));
  const target = reviewFixture().quantitative_ledger.targets[0];
  for (const [rule, expected] of [
    [{ mode: "exact", scope: "Protective efficacy", reason: "" }, "Exact match: Protective efficacy"],
    [{ mode: "compatible", scope: "Adult cohorts", reason: "Includes adult subgroups." }, "Compatible match: Adult cohorts"],
    [{ mode: "unknown", scope: "", reason: "Timing is ambiguous." }, "Scope needs review: Timing is ambiguous."],
    [{ mode: "unconstrained", scope: "", reason: "" }, "Does not control comparison"],
  ] as const) {
    target.comparison_contract.measure = rule;
    const before = JSON.stringify(target);
    const html = renderToStaticMarkup(React.createElement(TargetQualifierDetails, { target, dimension: "measure" }));
    assert.match(html, /Document says/);
    assert.ok(html.includes(expected));
    if (rule.mode === "exact" || rule.mode === "compatible") assert.match(html, /Evidence must match/);
    else assert.doesNotMatch(html, /Evidence must match/);
    if (rule.reason) assert.ok(html.includes(rule.reason));
    assert.equal(JSON.stringify(target), before);
  }
});

test("comparison exposes qualifier reasoning and separates non-controlling fields from matches", () => {
  const result = reviewFixture();
  const target = result.quantitative_ledger.targets[0];
  target.comparison_contract.population = { mode: "compatible", scope: "Adults", reason: "The target allows adult cohorts." };
  const measurement = result.conformity[0].excluded_measurements[0];
  measurement.semantic_assessment.dimensions.population = {
    source: { state: "specified", value: "Adults aged 18–65", other: "" },
    compatibility: { state: "yes", reason: "The reported age range falls within the required adult population." },
  };
  measurement.semantic_assessment.dimensions.regimen.compatibility.reason = "No regimen restriction was imposed.";
  const before = JSON.stringify(result);
  const html = renderToStaticMarkup(React.createElement(QuantitativeReviewCheckpoint, {
    result, onNewAnalysis: () => {}, onReview: () => {}, onAcceptRecommendations: () => {},
    readyToFinalize: false, onFinalize: () => {},
  }));
  assert.match(html, /The reported age range falls within the required adult population/);
  assert.match(html, /The target allows adult cohorts/);
  const disclosure = html.match(/<details[\s\S]*?<\/details>/)?.[0] ?? "";
  assert.match(disclosure, /Does not control comparison/);
  assert.match(disclosure, /No regimen restriction was imposed/);
  assert.doesNotMatch(disclosure, />Aligned</);
  assert.equal(JSON.stringify(result), before);
});

test("review and final comparator details expose source ownership and only cited qualifier passages", () => {
  const result = reviewFixture();
  const target = result.quantitative_ledger.targets[0];
  const measurement = result.conformity[0].excluded_measurements[0];
  measurement.semantic_assessment.source_ownership = { state: "unknown", reason: "The passage may be describing another study's estimate." };
  const { AdmittedMeasurement } = loadComponent(fileURLToPath(new URL("../components/comparator-cohort.tsx", import.meta.url)), {}, ["AdmittedMeasurement"]);
  const { ExcludedMeasurement } = loadComponent(fileURLToPath(new URL("../components/excluded-measurements.tsx", import.meta.url)), {}, ["ExcludedMeasurement"]);
  const { DocumentSourceProvider } = loadComponent(fileURLToPath(new URL("../components/document-source-trace.tsx", import.meta.url)));
  for (const child of [
    React.createElement(QuantitativeReviewCheckpoint, { result, onNewAnalysis: () => {}, onReview: () => {}, onAcceptRecommendations: () => {}, readyToFinalize: false, onFinalize: () => {} }),
    React.createElement(AdmittedMeasurement, { measurement, target, unit: "%" }),
    React.createElement(ExcludedMeasurement, { measurement, target, unit: "%", title: "Source" }),
  ]) {
    const html = renderToStaticMarkup(React.createElement(DocumentSourceProvider, { blocks: result.blocks }, child));
    assert.match(html, /The passage may be describing another study/);
    assert.match(html, /Source ownership/);
    assert.match(html, /Uncertain/);
    assert.match(html, /In document: 1 source passage/);
  }
});

test("qualifier citations never borrow the overall target passage when their own provenance is empty", () => {
  const { TargetQualifierSource } = loadComponent(fileURLToPath(new URL("../components/scout-comparison.tsx", import.meta.url)));
  const target = reviewFixture().quantitative_ledger.targets[0];
  assert.equal(renderToStaticMarkup(React.createElement(TargetQualifierSource, { target, dimension: "population" })), "");
  assert.match(renderToStaticMarkup(React.createElement(TargetQualifierSource, { target, dimension: "measure" })), /In document: 1 source passage/);
});

test("completed evidence remains correctable and advancement stays outside the page header", () => {
  const html = renderToStaticMarkup(React.createElement(QuantitativeReviewCheckpoint, {
    result: evidenceReviewFixture("completed"), onNewAnalysis: () => {}, onReview: () => {},
    onAcceptRecommendations: () => {},
    readyToFinalize: true, onFinalize: () => {},
  }));
  assert.match(html, /Reject comparator/);
  assert.match(html, /Admit comparator/);
  assert.match(html, /Finalize result/);
  assert.doesNotMatch(html.match(/<header[\s\S]*?<\/header>/)?.[0] ?? "", /Finalize result/);
});

test("a single actionable recommendation uses singular copy in both checkpoints", () => {
  const result = reviewFixture();
  result.conformity[0].excluded_measurements[0].ai_recommendation = "admit";
  const evidence = renderToStaticMarkup(React.createElement(QuantitativeReviewCheckpoint, {
    result, onNewAnalysis: () => {}, onReview: () => {}, onAcceptRecommendations: () => {},
    readyToFinalize: false, onFinalize: () => {},
  }));
  assert.match(evidence, />Accept 1 AI recommendation<\/button>/);
  const targetResult = reviewFixture("target_review");
  const target = renderToStaticMarkup(React.createElement(DocumentTargetReviewCheckpoint, {
    result: targetResult, busy: false, stage: null, progress: null,
    onNewAnalysis: () => {}, onTargetDecision: () => {}, onStatementDecision: () => {},
    onAcceptRecommendations: () => {}, onContinue: () => {},
  }));
  assert.match(target, />Accept 1 AI recommendation<\/button>/);
});

test("one overview contains single estimates and grouped alternatives without presenting an arbitrary alternative as the group", () => {
  const html = renderToStaticMarkup(React.createElement(QuantitativeReviewCheckpoint, {
    result: reviewFixture(), onNewAnalysis: () => {}, onReview: () => {}, onAcceptRecommendations: () => {},
    readyToFinalize: false, onFinalize: () => {},
  }));
  assert.match(html, /85% compared with a target of/);
  assert.match(html, /2 estimates compared with a target of/);
  assert.match(html, /Read full excerpt/);
  assert.match(html, /End of complete quotation/);
  assert.match(html, /Reject comparator/);
  assert.doesNotMatch(html, /type="radio"/);
});

const estimates = [
  { candidate_id: "a", admission_status: "rejected", ai_recommendation: "admit", expression: { kind: "point_estimate", value: 70, unit: "%" }, source_quote: "First estimate.", source_record_id: "Study A" },
  { candidate_id: "b", admission_status: "approved", ai_recommendation: "flag", expression: { kind: "point_estimate", value: 90, unit: "%" }, source_quote: "Second estimate.", source_record_id: "Study A" },
].map(item => ({ ...item, evidence_unit: {
  status: "record_level", group: { state: "not_specified", value: "", other: "" },
  cohort: { state: "not_specified", value: "", other: "" }, reason: "One source population.",
} }));

test("completed estimate groups open on the admitted estimate, not an old AI recommendation", () => {
  assert.equal(defaultReviewEstimateId(estimates), "b");
  assert.equal(defaultReviewEstimateId(estimates.map(item => ({ ...item, admission_status: "needs_review" }))), "a");
  assert.equal(defaultReviewEstimateId(estimates.map(item => ({ ...item, admission_status: "needs_review", ai_recommendation: "flag" }))), null);
  assert.equal(defaultReviewEstimateId(estimates.map(item => ({ ...item, admission_status: "rejected" }))), "a");
});

test("estimate choices expose native mutually exclusive controls and recorded statuses", () => {
  const html = renderToStaticMarkup(React.createElement(ReviewEstimateChoices, {
    measurements: estimates, selectedId: "b", onSelect: () => {}, pending: false,
  }));
  const radios = html.match(/<input[^>]+>/g) ?? [];
  assert.equal(radios.length, 2);
  assert.ok(radios.every(radio => radio.includes('type="radio"')));
  assert.equal(radios[0].match(/name="([^"]+)"/)?.[1], radios[1].match(/name="([^"]+)"/)?.[1]);
  assert.ok(!radios[0].includes('checked=""'));
  assert.ok(radios[1].includes('checked=""'));
  assert.match(html, /Admitted/);
  assert.match(html, /Rejected/);
  assert.match(html, /<fieldset/);
});

test("checkpoint headers reserve an action column and stack controls on small screens", () => {
  for (const labels of [
    ["Continue to evidence", "New analysis"],
    ["Continuing…", "New analysis"],
    ["Undo last decision", "Finalize result", "New analysis"],
  ]) {
    const html = renderToStaticMarkup(React.createElement(ReviewCheckpointHeader, {
      eyebrow: "Review", title: "Review document targets", description: "Check the source.",
      help: "Review help", completed: 1, total: 1, progressLabel: "Review progress",
      actions: labels.map((label) => React.createElement("button", { key: label }, label)),
    }));
    assert.match(html, /lg:grid-cols-\[minmax\(0,1fr\)_auto\]/);
    assert.match(html, /flex-col items-stretch sm:flex-row sm:flex-nowrap sm:justify-end/);
    for (const label of labels) assert.ok(html.includes(label));
    assert.match(html, /aria-valuenow="1"/);
  }
  const footer = renderToStaticMarkup(React.createElement(ReviewActions, {
    children: React.createElement("button", null, "Admit comparator"),
  }));
  assert.match(footer, /flex-wrap items-center/);
  assert.doesNotMatch(footer, /flex-col|sm:flex-nowrap/);
});

test("review rows preserve shared status tones independently of selection", () => {
  for (const [tone, label, sharedTone] of [
    ["positive", "Admitted", "success"],
    ["warning", "Needs review", "warning"],
    ["neutral", "Rejected", "neutral"],
  ] as const) {
    for (const selected of [false, true]) {
      const html = renderToStaticMarkup(React.createElement(ReviewListRow, {
        tone, status: label, selected, onSelect: () => {},
        title: "Document target", subtitle: "24 months", detail: "Cited evidence",
      }));
      const status = html.match(new RegExp(`<span[^>]*class="([^"]*)"[^>]*>${label}</span>`));
      assert.ok(status, `Visible ${label} status`);
      for (const token of TONE_TINT[sharedTone].split(" ")) {
        assert.ok(status[1].split(" ").includes(token), `${label} uses shared ${sharedTone} treatment`);
      }
      assert.equal(html.includes('aria-current="true"'), selected);
    }
  }
});
