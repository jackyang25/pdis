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
  variables: [],
  search_plan: [],
  matches: [],
  assessments: [],
  conformity: [{
    attribute_ref: "efficacy",
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
  assert.equal(packed.version, 22);
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
  assert.equal(packed.version, 22);
  assert.equal(packed.result_type, "aligner");
  assert.equal("blocks" in packed.analysis.alignment, false);
  assert.equal(packed.source_documents.length, 2);
  assert.deepEqual(unpackAlignerResult(packed), result);
});

test("current Scout export and import preserve the canonical result exactly", () => {
  const packed = packScoutResult(scout);
  assert.equal(packed.version, 22);
  assert.deepEqual(unpackScoutResult(packed), scout);
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

test("current-version measurements missing the semantic assessment fail closed", () => {
  const malformed = structuredClone(packScoutResult(scout)) as any;
  malformed.analysis.conformity[0].calibration_status = "sufficient";
  malformed.analysis.conformity[0].measurements = [{
    candidate_id: "qm-malformed",
    expression: { kind: "point_estimate", unit: "%", value: 82, lower: null, upper: null, comparator: "" },
    source_quote: "Efficacy was 82%.",
  }];

  const imported = unpackScoutResult(malformed);

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

  assert.equal(imported.variables[0].quantitative_targets.length, 1);
  assert.equal(imported.variables[0].quantitative_targets[0].id, "qt-123");
  assert.equal(
    imported.variables[0].quantitative_targets[0].semantic_profile.measure.state,
    "specified",
  );
  assert.deepEqual(imported.variables[0].quantitative_targets[0].provenance_spans, [{
    quote: "Target efficacy is at least 80%.",
    block_ids: ["document/b-0001"],
  }]);
});
