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
    sections: [],
    document_findings: [],
    consistency_status: "complete",
    assessment_status: "complete",
    org: "bmgf",
    source_type: "itpp",
    intervention_class: "vaccine",
    indication: "malaria",
    blocks: [block],
  },
};

const scout: ScoutResponse = {
  phase: "final",
  published_since: "",
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
  development_landscape: [{
    projection_id: "dp-trial-1",
    name: "Comparator vaccine trial",
    sponsors: ["Example sponsor"],
    phases: ["Phase 2"],
    statuses: ["Completed"],
    record_types: ["clinical_trial"],
    record_ids: ["NCT00000001"],
    attribute_refs: ["efficacy"],
    source_role: "comparator",
    target_relationship: "analogous",
    target_relationship_reason: "The trial evaluates another product in the same intervention class.",
    supporting_findings: [],
  }],
  safety_observations: [{
    projection_id: "so-faers-1",
    product_name: "Comparator vaccine",
    record_type: "reported_event",
    source_system: "faers",
    label: "Headache",
    detail: "A source-supplied FAERS event category.",
    report_count: 12,
    qualification: "Spontaneous report counts do not measure incidence or causality.",
    attribute_refs: ["safety"],
    source_role: "comparator",
    target_relationship: "adjacent",
    target_relationship_reason: "The report concerns a related product class.",
    supporting_findings: [],
  }],
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
  // Two versions, checked separately: the envelope is the wrapper all three tools
  // share, and the analysis version belongs to this tool alone. An Inspector change
  // bumps only its own entry, so a saved Scout result stays readable.
  assert.equal(packed.envelope_version, 1);
  assert.equal(packed.analysis_version, 2);
  assert.equal(packed.state, "final");
  assert.equal(packed.result_type, "inspector");
  assert.equal("blocks" in packed.analysis.inspection, false);
  assert.deepEqual(unpackInspectorResult(packed), inspection);
});

/** Three documents and the two comparisons they resolve, matching the config. */
function alignerResult(): AlignerResponse {
  return {
    alignment: {
      documents: [
        { doc_id: "doc", source_type: "itpp", display_name: "iTPP" },
        { doc_id: "candidate", source_type: "ctpp", display_name: "cTPP" },
        { doc_id: "later", source_type: "ipdp", display_name: "IPDP" },
      ],
      edges: [
        {
          edge_id: "itpp-to-ctpp",
          reference_doc_id: "doc",
          comparison_doc_id: "candidate",
          question: "Meets the bar?",
        },
        {
          edge_id: "ctpp-to-ipdp",
          reference_doc_id: "candidate",
          comparison_doc_id: "later",
          question: "Delivers it?",
        },
      ],
      org: "bmgf",
      intervention_class: "vaccine",
      indication: "malaria",
      blocks: [
        block,
        { ...block, id: "candidate:1", doc_id: "candidate" },
        { ...block, id: "later:1", doc_id: "later" },
      ],
      findings: [
        {
          requirement_id: "itpp-to-ctpp/r-001",
          edge_id: "itpp-to-ctpp",
          requirement: "Annual dosing.",
          reference_spans: [{ quote: "cited", block_ids: [block.id] }],
          verdict: "falls_short",
          statement: "The candidate states six-monthly dosing.",
          comparison_spans: [{ quote: "cited", block_ids: ["candidate:1"] }],
        },
      ],
    },
  };
}

test("current Aligner results separate every source document", () => {
  const result = alignerResult();
  const packed = packAlignerResult(result);
  // 3, because findings returned: a v2 file carries none, so it would render as a run
  // that compared nothing — indistinguishable from one that found nothing wrong.
  assert.equal(packed.analysis_version, 3);
  // Three, not two: how many documents a run holds is Aligner's configuration to
  // decide, and nothing in the envelope assumes a number.
  assert.equal(packed.source_documents.length, 3);
  assert.deepEqual(unpackAlignerResult(packed), result);
});

test("an Aligner comparison must name documents the file carries", () => {
  const dangling = alignerResult();
  dangling.alignment.edges[0].reference_doc_id = "absent";
  assert.throws(() => packAlignerResult(dangling), /does not carry/);
});

test("an Aligner result with no comparison is refused", () => {
  const uncompared = alignerResult();
  uncompared.alignment.edges = [];
  assert.throws(() => packAlignerResult(uncompared), /no comparison/);
});

test("current Scout results round-trip exactly", () => {
  const packed = packScoutResult(scout);
  const unpacked = unpackScoutResult(packed);
  assert.deepEqual(unpacked, scout);
  assert.equal(unpacked.development_landscape[0]?.source_role, "comparator");
  assert.equal(unpacked.development_landscape[0]?.target_relationship, "analogous");
  assert.equal(unpacked.safety_observations[0]?.record_type, "reported_event");
  assert.equal(unpacked.safety_observations[0]?.source_system, "faers");
  assert.equal(unpacked.safety_observations[0]?.label, "Headache");
  assert.equal(unpacked.safety_observations[0]?.report_count, 12);
  assert.equal(unpacked.safety_observations[0]?.source_role, "comparator");
  assert.equal(unpacked.safety_observations[0]?.target_relationship, "adjacent");
  assert.equal(unpacked.safety_observations[0]?.supporting_findings.length, 0);
});

test("Scout export rejects an unfinished review draft", () => {
  const draft = structuredClone(scout);
  draft.phase = "target_review";
  assert.throws(() => packScoutResult(draft), /quantitative evidence contract/);
});

test("imports require the current final envelope", () => {
  const missingState = structuredClone(packScoutResult(scout)) as any;
  delete missingState.state;
  assert.throws(() => unpackScoutResult(missingState), /complete, final scout result/);

  assert.throws(() => unpackScoutResult(scout), /not a PDIS result file/);
});

test("an older envelope says every saved result must be re-run", () => {
  const stale = structuredClone(packScoutResult(scout)) as any;
  stale.envelope_version = 0;
  assert.throws(() => unpackScoutResult(stale), /every saved result must be re-run/);
});

test("an older analysis version names only the tool that changed", () => {
  // The reason the two are separate. A single number meant an Inspector change
  // rejected saved Scout files that were still perfectly readable, and the message
  // told everyone to re-run everything.
  const stale = structuredClone(packScoutResult(scout)) as any;
  stale.analysis_version = 0;
  assert.throws(() => unpackScoutResult(stale), /re-run the scout analysis/);
});

test("one tool's analysis version does not gate another's", () => {
  const scoutFile = packScoutResult(scout);
  const inspectorFile = packInspectorResult(inspection);

  assert.equal(scoutFile.envelope_version, inspectorFile.envelope_version);
  assert.deepEqual(unpackScoutResult(scoutFile), scout);
  assert.deepEqual(unpackInspectorResult(inspectorFile), inspection);
});

test("current Scout artifacts require complete projection roles", () => {
  const malformed = structuredClone(packScoutResult(scout)) as any;
  delete malformed.analysis.development_landscape[0].target_relationship;
  assert.throws(
    () => unpackScoutResult(malformed),
    /projection role contract/,
  );
});

test("current Scout artifacts require complete safety observations", () => {
  const malformed = structuredClone(packScoutResult(scout)) as any;
  delete malformed.analysis.safety_observations[0].source_system;
  assert.throws(
    () => unpackScoutResult(malformed),
    /safety observation contract/,
  );
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
    /quantitative evidence contract/,
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
    /quantitative evidence contract/,
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

  // Named by document type, so a three-document run reads as what it compared
  // rather than as two filenames with a third silently dropped.
  assert.equal(alignerResultFilename(alignerResult()), "itpp-ctpp-ipdp-aligner.json");
});
