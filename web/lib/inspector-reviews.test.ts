import assert from "node:assert/strict";
import test from "node:test";
import { projectInspectionReview } from "./inspector-reviews.ts";
import { packInspectorResult, unpackInspectorResult } from "./result-file.ts";
import type { InspectionResult, InspectionReview } from "./api.ts";

export function reviewFixture(id = "template"): InspectionReview {
  return {
    rubric: { id, revision: "1", display_name: id, authority: "Authored rubric",
      scope: "Document content only", evidence_scope: "whole_document", stage_guidance: "Planning evidence is sufficient.", mirrors: null,
      sources: [{ id: "source", title: "Source guideline", revision: "2025", url: "https://example.org/guideline" }],
      requirements: [{ id: `${id}::unit`, section_name: "Plan", variable_name: null,
        description: "Describe the plan", expectations: "State the planned work", source_refs: ["source"] }] },
    assessment_status: "complete",
    sections: [{ section_name: "Plan", is_present: null, mapped_block_ids: [],
      units: [{ id: `${id}::unit`, section_name: "Plan", variable_name: null,
        verdict: "specified", statement: "", optional: false, cited_block_ids: ["doc:1"], rank: 0 }],
      verdict_counts: { specified: 1, not_present: 0, placeholder: 0, insufficient: 0, vague: 0, section_conflict: 0, not_applicable: 0 } }],
  };
}

export function inspectionFixture(): InspectionResult {
  return { doc_id: "doc", org: "bmgf", source_type: "ipdp", intervention_class: "drug", indication: "malaria",
    reviews: [reviewFixture(), reviewFixture("ich")], applicability_facts: {},
    rubric_resolutions: ["template", "ich"].map(id => ({ rubric_id: id, display_name: id,
      status: "included", reason_code: "profile", reason: "Included by profile" })),
    assessment_status: "complete", consistency_status: "complete", document_findings: [],
    blocks: [{ id: "doc:1", doc_id: "doc", ordinal: 1, block_type: "paragraph", content: "Plan",
      heading_stack: [], section_label: "Other", structural_meta: {}, style_hint: {},
      image: { media_type: "image/png", data_base64: "YWJj", sha256: "hash", source_media_type: "image/png" } }] };
}

test("selected review is a non-mutating projection sharing the retained blocks", () => {
  const run = inspectionFixture();
  const projected = projectInspectionReview(run, "ich");
  assert.equal(projected.sections, run.reviews[1].sections);
  assert.equal(projected.blocks, run.blocks);
  assert.equal(projected.rubric.id, "ich");
  assert.equal("sections" in run, false);
  assert.throws(() => projectInspectionReview(run, "missing"), /rubric/i);
});

test("multi-rubric portable export retains every review, source snapshot and image once", () => {
  const response = { inspection: inspectionFixture() };
  const packed = packInspectorResult(response);
  assert.equal(packed.analysis_version, 3);
  assert.equal(packed.source_documents.length, 1);
  assert.deepEqual(unpackInspectorResult(JSON.parse(JSON.stringify(packed))), response);
});

test("template library provenance is portable and rejects executable links", () => {
  const run = inspectionFixture();
  run.reviews[0].rubric.reference_url = "https://example.org/template-library";
  const packed = packInspectorResult({ inspection: run });
  assert.equal(unpackInspectorResult(packed).inspection.reviews[0].rubric.reference_url,
    "https://example.org/template-library");
  run.reviews[0].rubric.reference_url = "javascript:alert(1)";
  assert.throws(() => packInspectorResult({ inspection: run }), /reference/i);
});

test("v2 imports wrap historical sections without inventing a known rubric revision", () => {
  const run = inspectionFixture();
  const { reviews, applicability_facts, rubric_resolutions, blocks, ...base } = run;
  const packed = packInspectorResult({ inspection: run });
  const historical = { ...packed, analysis_version: 2, analysis: { inspection: { ...base, sections: reviews[0].sections } } };
  const imported = unpackInspectorResult(historical).inspection;
  assert.deepEqual(imported.reviews[0].sections, reviews[0].sections);
  assert.equal(imported.reviews[0].rubric.revision, null);
  assert.deepEqual(imported.reviews[0].rubric.requirements, []);
  assert.deepEqual(imported.blocks, blocks);
  assert.equal("reviews" in historical.analysis.inspection, false);
});

test("current files cannot masquerade as multi-rubric runs without review metadata", () => {
  const packed = packInspectorResult({ inspection: inspectionFixture() });
  const invalid = structuredClone(packed);
  invalid.analysis.inspection.reviews = [];
  assert.throws(() => unpackInspectorResult(invalid), /review/i);
});

test("a requirement cannot displace another unit's saved authority", () => {
  const run = inspectionFixture();
  const review = run.reviews[0];
  review.sections[0].units.push({ ...review.sections[0].units[0], id: "template::second" });
  review.rubric.requirements.push({ ...review.rubric.requirements[0] });
  assert.throws(() => packInspectorResult({ inspection: run }), /requirements/i);
});

test("a rubric cannot be reported as both assessed and needing context", () => {
  const run = inspectionFixture();
  run.rubric_resolutions.push({ ...run.rubric_resolutions[0], status: "needs_context" });
  assert.throws(() => packInspectorResult({ inspection: run }), /resolution/i);
});
