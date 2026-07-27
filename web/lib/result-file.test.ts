import assert from "node:assert/strict";
import test from "node:test";

import type { AlignerResponse, ContentBlock, InspectorResponse, ScoutResponse } from "./api.ts";
import {
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

test("new portable results use the Inspector contract", () => {
  const packed = packInspectorResult(inspection);
  assert.equal(packed.version, 34);
  assert.equal(packed.state, "final");
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
  assert.equal(packed.version, 34);
  assert.equal(packed.state, "final");
  assert.equal(packed.result_type, "aligner");
  assert.equal("blocks" in packed.analysis.alignment, false);
  assert.equal(packed.source_documents.length, 2);
  assert.deepEqual(unpackAlignerResult(packed), result);
});

test("current Scout export and import preserve the canonical result exactly", () => {
  const packed = packScoutResult(scout);
  assert.equal(packed.version, 34);
  assert.equal(packed.state, "final");
  assert.deepEqual(unpackScoutResult(packed), scout);
});

test("Scout export rejects a quantitative review draft", () => {
  const draft = structuredClone(scout);
  draft.conformity[0].excluded_measurements = [{
    candidate_id: "pending",
    expression: { kind: "point_estimate", value: 82, lower: null, upper: null, comparator: "", unit: "%" },
    url: "https://example.test/study",
    insight_id: "insight-1",
    source_quote: "The result was 82%.",
    source_record_id: "doi:example",
    source_identity_status: "canonical",
    evidence_unit_id: "doi:example/unit:record",
    evidence_unit: {
      status: "record_level",
      group: { state: "not_specified", value: "", other: "" },
      cohort: { state: "not_specified", value: "", other: "" },
      reason: "One aggregate source group.",
    },
    semantic_assessment: {} as any,
    semantic_status: "comparable",
    semantic_reason: "Compatible result.",
    evidence_mode: "prose",
    ai_recommendation: "flag",
    ai_review_reason: "Manual review required.",
    admission_status: "needs_review",
    admission_reason: "Review required.",
    inclusion_reason: "",
    exclusion_reasons: ["Review required."],
    age_months: null,
  }];

  assert.throws(() => packScoutResult(draft), /review is incomplete/);
});

test("current portable envelopes must explicitly be final", () => {
  const malformed = structuredClone(packScoutResult(scout)) as any;
  delete malformed.state;

  assert.throws(
    () => unpackScoutResult(malformed),
    /invalid or incomplete pdis.result envelope/,
  );
});

test("version 26 prose comparators migrate to review candidates", () => {
  const previous = structuredClone(packScoutResult(scout)) as any;
  previous.version = 26;
  const measurement = {
    candidate_id: "candidate-1",
    expression: { kind: "point_estimate", value: 82, lower: null, upper: null, comparator: "", unit: "%" },
    url: "https://example.test/study",
    insight_id: "insight-1",
    source_quote: "The result was 82%.",
    source_record_id: "doi:example",
    source_identity_status: "canonical",
    semantic_assessment: {},
    semantic_status: "comparable",
    semantic_reason: "Compatible result.",
    inclusion_reason: "Previously admitted automatically.",
    exclusion_reasons: [],
    age_months: null,
  };
  previous.analysis.conformity[0].measurements = [measurement];
  previous.analysis.conformity[0].benchmark_count = 1;

  const imported = unpackScoutResult(previous);
  assert.equal(imported.conformity[0].benchmark_count, 0);
  assert.equal(imported.conformity[0].measurements.length, 0);
  assert.equal(imported.conformity[0].excluded_measurements.length, 1);
  assert.equal(
    imported.conformity[0].excluded_measurements[0].admission_status,
    "needs_review",
  );
});

test("version 25 Scout fields predate the complete API claim contract", () => {
  const previous = structuredClone(packScoutResult(scout)) as any;
  previous.version = 25;
  previous.analysis.variables = [{
    name: "efficacy",
    description: "Protective efficacy",
    block_ids: [block.id],
    document_target: "Source text",
    document_spans: [{ quote: "Source text", block_ids: [block.id] }],
    definition_mode: "fixed",
    target_resolved: true,
    target_resolution_reason: "Resolved from exact spans.",
    evidence_domain: "clinical",
    entities: [],
    quantitative_targets: [],
    quantitative_statement_dispositions: [],
    quantitative_target_status: "not_applicable",
    quantitative_target_status_reason: "No numeric target.",
  }];

  const imported = unpackScoutResult(previous);

  assert.equal(imported.variables[0].target_resolved, false);
  assert.deepEqual(imported.variables[0].document_spans, []);
});

test("version 20 Scout calibration predates atomic ownership and exact targets", () => {
  const previous = structuredClone(packScoutResult(scout)) as any;
  previous.version = 20;
  previous.analysis.conformity[0].calibration_status = "sufficient";

  const imported = unpackScoutResult(previous);

  assert.equal(imported.conformity[0].calibration_status, "legacy_unverified");
});

test("version 21 Scout calibration predates cited target semantics", () => {
  const previous = structuredClone(packScoutResult(scout)) as any;
  previous.version = 21;
  previous.analysis.conformity[0].calibration_status = "sufficient";

  const imported = unpackScoutResult(previous);

  assert.equal(imported.conformity[0].calibration_status, "legacy_unverified");
});

test("version 22 Scout calibration predates constrained semantic mapping", () => {
  const previous = structuredClone(packScoutResult(scout)) as any;
  previous.version = 22;
  previous.analysis.conformity[0].calibration_status = "sufficient";

  const imported = unpackScoutResult(previous);

  assert.equal(imported.conformity[0].calibration_status, "legacy_unverified");
});

test("current final artifacts with malformed measurements are rejected", () => {
  const malformed = structuredClone(packScoutResult(scout)) as any;
  malformed.analysis.conformity[0].calibration_status = "sufficient";
  malformed.analysis.conformity[0].measurements = [{
    candidate_id: "qm-malformed",
    expression: { kind: "point_estimate", unit: "%", value: 82, lower: null, upper: null, comparator: "" },
    source_quote: "Efficacy was 82%.",
  }];

  assert.throws(
    () => unpackScoutResult(malformed),
    /incomplete quantitative evidence contract/,
  );
});

test("version 28 Scout calibration is viewable but predates evidence-unit identity", () => {
  const previous = structuredClone(packScoutResult(scout)) as any;
  previous.version = 28;
  previous.analysis.conformity[0].calibration_status = "sufficient";

  const imported = unpackScoutResult(previous);
  assert.equal(imported.conformity[0].calibration_status, "legacy_unverified");
});

test("Scout download names are derived from the stable source document ID", () => {
  const named = {
    ...scout,
    blocks: [{ ...block, doc_id: "DRAFT AIV iTPP v1 13July2016" }],
  };
  assert.equal(
    scoutResultFilename(named),
    "draft-aiv-itpp-v1-13july2016-scout.json",
  );
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

test("older Scout calibration is marked unverified at the import boundary", () => {
  const legacy = {
    schema: "pdis.result",
    version: 11,
    result_type: "scout",
    analysis: {
      conformity: [{
        attribute_ref: "efficacy",
        target_value: 85,
        comparator: ">=",
        unit: "%",
        conformity: 0.5,
        lower: 0.25,
        upper: 0.75,
        verdict: "Mixed / indeterminate alignment",
        measurements: [
          { value: 80, unit: "%" },
          { value: 90, unit: "%" },
        ],
      }],
    },
    source_documents: [],
  };

  const imported = unpackScoutResult(legacy);
  assert.equal(imported.conformity[0].benchmark_count, 2);
  assert.equal(imported.conformity[0].benchmark_median, 85);
  assert.equal(imported.conformity[0].ambition_percentile, 0.5);
  assert.equal(imported.conformity[0].calibration_status, "legacy_unverified");
  assert.equal(imported.conformity[0].target_meeting_count, 1);
  assert.equal(imported.conformity[0].target_meeting_rate, 0.5);
});

test("an old exclusion ledger without immutable span evidence is also unverified", () => {
  const imported = unpackScoutResult({
    schema: "pdis.result",
    version: 13,
    result_type: "scout",
    analysis: {
      conformity: [{
        attribute_ref: "efficacy",
        target_id: "qt-old",
        target_role: "threshold",
        target_value: 80,
        comparator: ">=",
        unit: "%",
        target_quote: "Target efficacy is at least 80%.",
        target_meeting_count: 0,
        target_meeting_rate: 0,
        verdict: "No valid cohort",
        measurements: [],
        excluded_measurements: [{
          value: 82,
          unit: "%",
          source_quote: "Efficacy was 82%.",
        }],
      }],
    },
    source_documents: [],
  });

  assert.equal(imported.conformity[0].calibration_status, "legacy_unverified");
});

test("version 16 calibration is unverified under the semantic-profile contract", () => {
  const imported = unpackScoutResult({
    schema: "pdis.result",
    version: 16,
    result_type: "scout",
    analysis: {
      conformity: [{
        attribute_ref: "efficacy",
        target_id: "qt-v16",
        target_role: "threshold",
        target_value: 80,
        comparator: ">=",
        unit: "%",
        target_quote: "Target efficacy is at least 80%.",
        target_meeting_count: 0,
        target_meeting_rate: 0,
        verdict: "No cohort",
        calibration_status: "sufficient",
        measurements: [],
        excluded_measurements: [],
      }],
    },
    source_documents: [],
  });

  assert.equal(imported.conformity[0].calibration_status, "legacy_unverified");
});

test("version 17 calibration is unverified under the passage-expression contract", () => {
  const imported = unpackScoutResult({
    schema: "pdis.result",
    version: 17,
    result_type: "scout",
    analysis: {
      conformity: [{
        attribute_ref: "efficacy",
        target_id: "qt-v17",
        target_role: "threshold",
        target_value: 80,
        comparator: ">=",
        unit: "%",
        target_quote: "Target efficacy is at least 80%.",
        target_meeting_count: 0,
        target_meeting_rate: 0,
        verdict: "No cohort",
        calibration_status: "sufficient",
        measurements: [],
        excluded_measurements: [],
      }],
    },
    source_documents: [],
  });

  assert.equal(imported.conformity[0].calibration_status, "legacy_unverified");
});

test("version 18 calibration predates source-ownership admission", () => {
  const imported = unpackScoutResult({
    schema: "pdis.result",
    version: 18,
    result_type: "scout",
    analysis: {
      variables: [],
      matches: [],
      conformity: [{
        attribute_ref: "efficacy",
        target_id: "qt-v18",
        target_role: "threshold",
        target_value: 80,
        comparator: ">=",
        unit: "%",
        target_quote: "Target efficacy is at least 80%.",
        target_meeting_count: 0,
        target_meeting_rate: 0,
        verdict: "No validated comparator cohort",
        calibration_status: "insufficient",
        measurements: [],
        excluded_measurements: [],
        source_dispositions: [],
      }],
    },
    source_documents: [],
  });

  assert.equal(imported.conformity[0].calibration_status, "legacy_unverified");
});

test("unversioned Scout calibration cannot claim the current quantitative contract", () => {
  const imported = unpackScoutResult({
    variables: [],
    matches: [],
    assessments: [],
    precedents: [],
    conformity: [{
      attribute_ref: "efficacy",
      target_id: "qt-unversioned",
      target_role: "threshold",
      target_value: 80,
      comparator: ">=",
      unit: "%",
      target_quote: "Target efficacy is at least 80%.",
      target_meeting_count: 0,
      target_meeting_rate: 0,
      verdict: "No cohort",
      calibration_status: "sufficient",
      measurements: [],
      excluded_measurements: [],
    }],
    search_plan: [],
    blocks: [],
  });

  assert.equal(imported.conformity[0]?.calibration_status, "legacy_unverified");
});

test("version 14 Scout targets migrate onto the canonical variable contract", () => {
  const imported = unpackScoutResult({
    schema: "pdis.result",
    version: 14,
    result_type: "scout",
    analysis: {
      variables: [{
        name: "efficacy",
        description: "Protective efficacy",
        block_ids: ["document/b-0001"],
        document_target: "Target efficacy is at least 80%.",
      }],
      conformity: [{
        attribute_ref: "efficacy",
        target_id: "qt-123",
        target_role: "threshold",
        target_value: 80,
        comparator: ">=",
        unit: "%",
        target_label: "threshold >=80%",
        target_quote: "Target efficacy is at least 80%.",
        doc_block_ids: ["document/b-0001"],
        target_meeting_count: 0,
        target_meeting_rate: 0,
        verdict: "No cohort",
      }],
    },
    source_documents: [{ doc_id: "document", blocks: [block] }],
  });

  assert.deepEqual(imported.variables[0].quantitative_target_ids, ["qt-123"]);
  assert.equal(imported.quantitative_ledger.targets[0].id, "qt-123");
  assert.equal(
    imported.quantitative_ledger.targets[0].semantic_profile.measure.state,
    "specified",
  );
  assert.deepEqual(imported.quantitative_ledger.targets[0].provenance_spans, [{
    quote: "Target efficacy is at least 80%.",
    block_ids: ["document/b-0001"],
  }]);
});
