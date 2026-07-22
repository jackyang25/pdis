import assert from "node:assert/strict";
import test from "node:test";

import type { AlignerResponse, ContentBlock, InspectorResponse } from "./api.ts";
import {
  packAlignerResult,
  packInspectorResult,
  unpackAlignerResult,
  unpackInspectorResult,
} from "./result-file.ts";

const block: ContentBlock = {
  id: "doc:1",
  doc_id: "doc",
  ordinal: 1,
  block_type: "paragraph",
  content: "Source text",
  heading_stack: [],
  section_label: "Overview",
  structural_meta: {},
  style_hint: {},
};

const inspection: InspectorResponse = {
  inspection: {
    doc_id: "doc",
    dimensions: {
      completeness: { grade: "A", issues: [], recommendation: "" },
      adherence: { grade: "A", issues: [], recommendation: "" },
      rigor: { grade: "A", issues: [], recommendation: "" },
    },
    top_issues: [],
    section_grades: [],
    cross_section_findings: [],
    org: "bmgf",
    source_type: "itpp",
    intervention_class: "vaccine",
    indication: "malaria",
    blocks: [block],
  },
};

test("new portable results use the Inspector contract", () => {
  const packed = packInspectorResult(inspection);
  assert.equal(packed.version, 11);
  assert.equal(packed.result_type, "inspector");
  assert.equal("inspection" in packed.analysis, true);
  assert.equal("blocks" in packed.analysis.inspection, false);
  assert.deepEqual(unpackInspectorResult(packed), inspection);
});

test("Aligner results separate both source documents from the analysis", () => {
  const comparisonBlock = { ...block, id: "later:1", doc_id: "later" };
  const result: AlignerResponse = {
    alignment: {
      reference_document: { role: "reference", doc_id: "doc", source_type: "itpp", display_name: "iTPP" },
      comparison_document: { role: "comparison", doc_id: "later", source_type: "ipdp", display_name: "IPDP" },
      units: [],
      links: [],
      stats: { reference_units: 0, comparison_units: 0, aligned: 0, modified: 0, conflict: 0, missing: 0, introduced: 0 },
      org: "bmgf",
      intervention_class: "vaccine",
      indication: "malaria",
      unit_types: [],
      relations: [],
      blocks: [block, comparisonBlock],
    },
  };
  const packed = packAlignerResult(result);
  assert.equal(packed.version, 11);
  assert.equal(packed.result_type, "aligner");
  assert.equal("blocks" in packed.analysis.alignment, false);
  assert.equal(packed.source_documents.length, 2);
  assert.deepEqual(unpackAlignerResult(packed), result);
});

test("legacy Reviewer envelopes migrate only at import", () => {
  const { blocks: _blocks, ...legacyReview } = inspection.inspection;
  const legacy = {
    schema: "pdis.result",
    version: 9,
    result_type: "reviewer",
    analysis: { review: legacyReview },
    source_documents: [{ doc_id: "doc", blocks: [block] }],
  };

  assert.deepEqual(unpackInspectorResult(legacy), inspection);
});
