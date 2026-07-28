import assert from "node:assert/strict";
import test from "node:test";

import type { AlignerResponse, ContentBlock, InspectorResponse, ScoutResponse } from "./api.ts";
import {
  alignerResultFilename,
  inspectorResultFilename,
  packAlignerResult,
  packInspectorResult,
  packScoutResult,
  scoutResultFilename,
  unpackAlignerResult,
  unpackInspectorResult,
  unpackScoutResult,
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
    consistency_status: "complete",
    grading_status: "complete",
    org: "bmgf",
    source_type: "itpp",
    intervention_class: "vaccine",
    indication: "malaria",
    blocks: [block],
  },
};

const scout: ScoutResponse = {
  phase: "final",
  org: "bmgf",
  source_type: "itpp",
  intervention_class: "vaccine",
  indication: "malaria",
  context_validation: {
    status: "match",
    configured_indication: "malaria",
    document_indication: "malaria",
    reason: "The configured indication matches the document.",
    doc_block_ids: [block.id],
  },
  quantitative_ledger: {
    status: "not_applicable",
    reason: "No document statements were mapped.",
    block_ids: [],
    reviews: [],
    targets: [],
  },
  variables: [],
  search_plan: [],
  matches: [],
  assessments: [],
  conformity: [{
    attribute_refs: ["efficacy"],
    target_id: "qt-current",
    target_role: "threshold",
    target_value: 80,
    comparator: ">=",
    unit: "%",
    target_label: "protective efficacy >=80%",
    target_quote: "Target efficacy is at least 80%.",
    target_meeting_count: 0,
    target_meeting_rate: 0,
    verdict: "No validated comparator cohort",
    benchmark_count: 0,
    benchmark_minimum: null,
    benchmark_maximum: null,
    benchmark_mean: null,
    benchmark_median: null,
    benchmark_lower_quartile: null,
    benchmark_upper_quartile: null,
    benchmark_standard_deviation: null,
    target_percentile: null,
    ambition_percentile: null,
    calibration_status: "insufficient",
    doc_block_ids: [block.id],
    measurements: [],
    excluded_measurements: [],
    source_dispositions: [],
  }],
  precedents: [],
  development_landscape: [],
  safety_signals: [],
  stats: {
    queries: 0,
    findings: 0,
    unique_findings: 0,
    insights: 0,
    matches: 0,
    assessments: 0,
  },
  blocks: [block],
};

test("current Inspector results round-trip exactly", () => {
  const packed = packInspectorResult(inspection);
  assert.equal(packed.version, 36);
  assert.equal(packed.state, "final");
  assert.equal(packed.result_type, "inspector");
  assert.equal("blocks" in packed.analysis.inspection, false);
  assert.deepEqual(unpackInspectorResult(packed), inspection);
});

test("current Aligner results separate both source documents", () => {
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
  assert.equal(packed.source_documents.length, 2);
  assert.deepEqual(unpackAlignerResult(packed), result);
});

test("current Scout results round-trip exactly", () => {
  const packed = packScoutResult(scout);
  assert.deepEqual(unpackScoutResult(packed), scout);
});

test("Scout export rejects an unfinished review draft", () => {
  const draft = structuredClone(scout);
  draft.phase = "target_review";
  assert.throws(() => packScoutResult(draft), /review is incomplete/);
});

test("imports require the current final envelope", () => {
  const missingState = structuredClone(packScoutResult(scout)) as any;
  delete missingState.state;
  assert.throws(() => unpackScoutResult(missingState), /current, final scout result/);

  const oldVersion = structuredClone(packScoutResult(scout)) as any;
  oldVersion.version = 35;
  assert.throws(() => unpackScoutResult(oldVersion), /current, final scout result/);

  assert.throws(() => unpackScoutResult(scout), /current, final scout result/);
});

test("imports reject the wrong result type", () => {
  assert.throws(
    () => unpackScoutResult(packInspectorResult(inspection)),
    /expected a scout result, received inspector/,
  );
});

test("current Scout artifacts reject malformed evidence units", () => {
  const malformed = structuredClone(packScoutResult(scout)) as any;
  malformed.analysis.conformity[0].measurements = [{
    candidate_id: "qm-malformed",
    source_quote: "Efficacy was 82%.",
  }];
  assert.throws(
    () => unpackScoutResult(malformed),
    /incomplete quantitative evidence contract/,
  );
});

test("current Scout artifacts require a complete comparison contract", () => {
  const malformed = structuredClone(packScoutResult(scout)) as any;
  malformed.analysis.quantitative_ledger.targets = [{
    id: "qt-malformed",
    comparison_contract: {
      measure: { mode: "exact", scope: "protective efficacy", reason: "" },
    },
  }];
  assert.throws(
    () => unpackScoutResult(malformed),
    /incomplete quantitative evidence contract/,
  );
});

test("portable result filenames consistently use source IDs and tool names", () => {
  const namedScout = {
    ...scout,
    blocks: [{ ...block, doc_id: "DRAFT AIV iTPP v1 13July2016" }],
  };
  assert.equal(scoutResultFilename(namedScout), "draft-aiv-itpp-v1-13july2016-scout.json");

  const namedInspector = structuredClone(inspection);
  namedInspector.inspection.doc_id = "DRAFT AIV iTPP v1 13July2016";
  assert.equal(
    inspectorResultFilename(namedInspector),
    "draft-aiv-itpp-v1-13july2016-inspector.json",
  );

  const namedAligner = structuredClone({
    alignment: {
      reference_document: { doc_id: "Reference TPP" },
      comparison_document: { doc_id: "Candidate TPP" },
    },
  }) as AlignerResponse;
  assert.equal(
    alignerResultFilename(namedAligner),
    "reference-tpp-to-candidate-tpp-aligner.json",
  );
});
