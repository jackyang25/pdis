import assert from "node:assert/strict";
import test from "node:test";

import type { AlignerResponse, ContentBlock, InspectorResponse, ScoutResponse } from "./api.ts";
import {
  runFilename,
  runLabel,
  packAlignerResult,
  packInspectorResult,
  packScoutResult,
  readResultIdentity,
  unpackAlignerResult,
  unpackInspectorResult,
  unpackScoutResult,
} from "./result-file.ts";

/** The held run a file is written for; packing never mints identity of its own. */
const RUN = { id: "run-1", created_at: "2026-01-01T00:00:00.000Z" };

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
    reviews: [{ rubric: { id: "test", revision: null, updated_on: null, display_name: "Test", authority: "Test", scope: "Test", stage_guidance: "", mirrors: null, evidence_scope: "mapped_section", sources: [], requirements: [] }, sections: [], assessment_status: "complete" }],
    applicability_facts: {},
    rubric_resolutions: [{ rubric_id: "test", display_name: "Test", status: "included", reason_code: "test", reason: "Test" }],
    document_findings: [],
    consistency_status: "complete",
    consistency_failure_code: null,
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
    failure_code: "",
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
    target_meeting_rate: null,
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
    target_relationship_failure_code: "",
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
    target_relationship_failure_code: "",
    supporting_findings: [],
  }],
  stats: {
    queries: 0,
    findings: 0,
    unique_findings: 0,
    insights: 0,
    matches: 0,
    assessments: 0,
    announcements_read: 0,
    announcements_named: 0,
    announcements_failed: 0,
    announcements_failed_by_code: {},
  },
  retrieval_scope: {
    entries: [
      { dimension: "condition", value: "malaria", provenance: "header", block_ids: [] },
      { dimension: "intervention", value: "vaccine", provenance: "header", block_ids: [] },
      { dimension: "region", value: "", provenance: "unset", block_ids: [] },
    ],
  },
  reconciliations: [],
  not_searched_fields: [],
  blocks: [block],
};

test("current Inspector results round-trip exactly", () => {
  const packed = packInspectorResult(inspection, RUN);
  // Two versions, checked separately: the envelope is the wrapper all three tools
  // share, and the analysis version belongs to this tool alone. An Inspector change
  // bumps only its own entry, so a saved Scout result stays readable.
  assert.equal(packed.envelope_version, 1);
  assert.equal(packed.analysis_version, 4);
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
          reference_visual_block_ids: [],
          comparison_visual_block_ids: [],
          reference_spans: [{ quote: "cited", block_ids: [block.id] }],
          verdict: "falls_short",
          statement: "The candidate states six-monthly dosing.",
          comparison_spans: [{ quote: "cited", block_ids: ["candidate:1"] }],
        },
        {
          requirement_id: "ctpp-to-ipdp/r-001",
          edge_id: "ctpp-to-ipdp",
          requirement: "Six-monthly dosing.",
          reference_visual_block_ids: [],
          comparison_visual_block_ids: [],
          reference_spans: [{ quote: "cited", block_ids: ["candidate:1"] }],
          verdict: "meets",
          statement: "The plan states six-monthly dosing.",
          comparison_spans: [{ quote: "cited", block_ids: ["later:1"] }],
        },
      ],
    },
  };
}

test("current Aligner results separate every source document", () => {
  const result = alignerResult();
  const packed = packAlignerResult(result, RUN);
  // Visual references are distinct from quotations in version 4.
  assert.equal(packed.analysis_version, 4);
  // Three, not two: how many documents a run holds is Aligner's configuration to
  // decide, and nothing in the envelope assumes a number.
  assert.equal(packed.source_documents.length, 3);
  assert.deepEqual(unpackAlignerResult(packed), result);
});

test("an Aligner comparison must name documents the file carries", () => {
  const dangling = alignerResult();
  dangling.alignment.edges[0].reference_doc_id = "absent";
  assert.throws(() => packAlignerResult(dangling, RUN), /does not carry/);
});

test("Aligner v3 imports preserve text lineage without inventing visual references", () => {
  const original = alignerResult();
  const old = JSON.parse(JSON.stringify(packAlignerResult(original, RUN)));
  old.analysis_version = 3;
  for (const item of old.analysis.alignment.findings) {
    delete item.reference_visual_block_ids;
    delete item.comparison_visual_block_ids;
  }
  assert.deepEqual(unpackAlignerResult(old), original);
  assert.equal(old.analysis.alignment.findings[0].reference_visual_block_ids, undefined);
  old.analysis_version = 4;
  assert.throws(() => unpackAlignerResult(old), /visual citations/);
});

test("Aligner visual references must resolve to assets on the correct document side", () => {
  const result = alignerResult();
  const visual = { ...block, id: "doc/image", block_type: "image", image: {
    media_type: "image/png", source_media_type: "image/png", sha256: "test-image",
    data_base64: "cG5n", width: 1, height: 1,
  } };
  result.alignment.blocks.splice(1, 0, visual);
  const finding = result.alignment.findings[0];
  finding.reference_spans = [];
  finding.reference_visual_block_ids = [visual.id];
  assert.deepEqual(unpackAlignerResult(packAlignerResult(result, RUN)), result);
  finding.comparison_visual_block_ids = [visual.id];
  assert.throws(() => packAlignerResult(result, RUN), /own side/);
  finding.comparison_visual_block_ids = [];
  finding.reference_visual_block_ids = [block.id];
  assert.throws(() => packAlignerResult(result, RUN), /retained image/);
});

test("Aligner imports refuse visual references without an inspectable retained asset", () => {
  const result = alignerResult();
  const visual = { ...block, id: "doc/image", block_type: "image", image: {
    media_type: "image/png", source_media_type: "image/png", sha256: "test-image",
    data_base64: "cG5n", width: 1, height: 1,
  } };
  result.alignment.blocks.splice(1, 0, visual);
  result.alignment.findings[0].reference_spans = [];
  result.alignment.findings[0].reference_visual_block_ids = [visual.id];
  const packed = packAlignerResult(result, RUN);

  for (const image of [
    {},
    { media_type: "text/plain", data_base64: "cG5n" },
    { media_type: "image/png", data_base64: "   " },
  ]) {
    const malformed = structuredClone(packed) as any;
    malformed.source_documents
      .flatMap((document: any) => document.blocks)
      .find((source: any) => source.id === visual.id).image = image;
    assert.throws(() => unpackAlignerResult(malformed), /retained image/);
  }
});

test("an Aligner result with no comparison is refused", () => {
  const uncompared = alignerResult();
  uncompared.alignment.edges = [];
  assert.throws(() => packAlignerResult(uncompared, RUN), /no comparison/);
});

test("current Scout results round-trip exactly", () => {
  const packed = packScoutResult(scout, RUN);
  // 5: the reviewer's field selection, and `not_searched` for the fields it left out.
  assert.equal(packed.analysis_version, 5);
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
  assert.throws(() => packScoutResult(draft, RUN), /quantitative evidence contract/);
});

test("imports require the current final envelope", () => {
  const missingState = structuredClone(packScoutResult(scout, RUN)) as any;
  delete missingState.state;
  assert.throws(() => unpackScoutResult(missingState), /complete, final scout result/);

  assert.throws(() => unpackScoutResult(scout), /not a PDIS result file/);
});

test("an older envelope says every saved result must be re-run", () => {
  const stale = structuredClone(packScoutResult(scout, RUN)) as any;
  stale.envelope_version = 0;
  assert.throws(() => unpackScoutResult(stale), /every saved result must be re-run/);
});

test("an older analysis version names only the tool that changed", () => {
  // The reason the two are separate. A single number meant an Inspector change
  // rejected saved Scout files that were still perfectly readable, and the message
  // told everyone to re-run everything.
  const stale = structuredClone(packScoutResult(scout, RUN)) as any;
  stale.analysis_version = 0;
  assert.throws(() => unpackScoutResult(stale), /re-run the scout analysis/);
});

test("one tool's analysis version does not gate another's", () => {
  const scoutFile = packScoutResult(scout, RUN);
  const inspectorFile = packInspectorResult(inspection, RUN);

  assert.equal(scoutFile.envelope_version, inspectorFile.envelope_version);
  assert.deepEqual(unpackScoutResult(scoutFile), scout);
  assert.deepEqual(unpackInspectorResult(inspectorFile), inspection);
});

test("current Scout artifacts require complete projection roles", () => {
  const malformed = structuredClone(packScoutResult(scout, RUN)) as any;
  delete malformed.analysis.development_landscape[0].target_relationship;
  assert.throws(
    () => unpackScoutResult(malformed),
    /projection role contract/,
  );
});

test("current Scout artifacts require complete safety observations", () => {
  const malformed = structuredClone(packScoutResult(scout, RUN)) as any;
  delete malformed.analysis.safety_observations[0].source_system;
  assert.throws(
    () => unpackScoutResult(malformed),
    /safety observation contract/,
  );
});

test("imports reject the wrong result type", () => {
  assert.throws(
    () => unpackScoutResult(packInspectorResult(inspection, RUN)),
    /expected a scout result, received inspector/,
  );
});

test("current Scout artifacts reject malformed evidence units", () => {
  const malformed = structuredClone(packScoutResult(scout, RUN)) as any;
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
  const malformed = structuredClone(packScoutResult(scout, RUN)) as any;
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

test("download suggestions are bounded tool names, independent of source filenames", () => {
  for (const tool of ["inspector", "scout", "screener", "aligner", "drafter", "chunker"] as const) {
    assert.equal(runFilename(tool), `pdis-${tool}.json`);
  }
});

test("single-document run labels retain the source name without using it as a download name", () => {
  const namedScout = {
    ...scout,
    blocks: [{ ...block, doc_id: "DRAFT AIV iTPP v1 13July2016" }],
  };
  assert.equal(runLabel(namedScout, "scout"), "DRAFT AIV iTPP v1 13July2016");

  const namedInspector = structuredClone(inspection);
  namedInspector.inspection.doc_id = "DRAFT AIV iTPP v1 13July2016";
  assert.equal(
    runLabel(namedInspector, "inspector"),
    "DRAFT AIV iTPP v1 13July2016",
  );

  assert.equal(runLabel(alignerResult(), "aligner"), "iTPP · cTPP · IPDP");
});

test("a file carries the identity of the run it was written from", () => {
  // Minting a fresh id at packing made every download a stranger to the workspace that
  // wrote it, so re-importing a run just downloaded held it twice.
  const first = packScoutResult(scout, RUN);
  const second = packScoutResult(scout, RUN);
  assert.equal(first.id, RUN.id);
  assert.equal(first.created_at, RUN.created_at);
  assert.equal(second.id, first.id);
  assert.deepEqual(readResultIdentity(JSON.parse(JSON.stringify(first))), RUN);
});

test("a Scout file without its fields or matches is refused at the import boundary", () => {
  for (const field of ["variables", "matches"]) {
    const malformed = structuredClone(packScoutResult(scout, RUN)) as any;
    delete malformed.analysis[field];
    assert.throws(() => unpackScoutResult(malformed), new RegExp(`${field} is missing`));
  }
});

test("Scout keeps a model's verdict and a pipeline failure apart", () => {
  // `not_assessed` is recorded by code and always says why; a verdict is the model's and
  // carries no failure. A file mixing the two would read a failed call as a finding.
  const unassessed = structuredClone(scout);
  unassessed.context_validation = {
    ...unassessed.context_validation, status: "not_assessed", doc_block_ids: [], failure_code: "provider_error",
  };
  unassessed.development_landscape[0].target_relationship = "not_assessed";
  unassessed.development_landscape[0].target_relationship_failure_code = "response_truncated";
  assert.deepEqual(unpackScoutResult(packScoutResult(unassessed, RUN)), unassessed);

  const silent = structuredClone(unassessed);
  silent.development_landscape[0].target_relationship_failure_code = "";
  assert.throws(() => packScoutResult(silent, RUN), /not assessed without a known failure code/);

  const coded = structuredClone(scout);
  coded.context_validation.failure_code = "provider_error";
  assert.throws(() => packScoutResult(coded, RUN), /a verdict but carries a failure code/);

  const precedent = structuredClone(scout);
  precedent.precedents = [{
    attribute_ref: "efficacy", precedent: "not_assessed", outcome: "unknown", reason: "", doc_block_ids: [],
    coverage_insight_ids: [], outcome_insight_ids: [], supporting_insight_ids: [], supporting_findings: [],
    failure_code: "invalid_model_response",
  }];
  assert.throws(() => packScoutResult(precedent, RUN), /precedent outcome/);
});

test("Scout refuses a source cited twice in one list", () => {
  const finding = {
    url: "https://example.org/trial", title: "Trial", query: "q", retrieved_at: "2026-01-01T00:00:00Z",
    excerpt: "", published_at: null, source: "pubmed",
  };
  const repeated = structuredClone(scout);
  repeated.development_landscape[0].supporting_findings = [finding, { ...finding }];
  assert.throws(() => packScoutResult(repeated, RUN), /cites one source twice/);
});

test("Scout names the checks a failed numeric review failed, and only then", () => {
  const review = {
    unit_id: "u-1", block_id: block.id, quote: "Efficacy at least 80%.", classification: "mapping_failed" as const,
    reason: "Target mapping rejected.", attribute_refs: [], target_ids: [], review_status: "accepted_exclusion" as const,
  };
  const named = structuredClone(scout);
  named.quantitative_ledger.reviews = [{ ...review, failure_code: "invalid_target_mapping", issue_codes: ["invalid_target_quote"] }];
  assert.deepEqual(unpackScoutResult(packScoutResult(named, RUN)), named);

  const unnamed = structuredClone(scout);
  unnamed.quantitative_ledger.reviews = [{ ...review, failure_code: "invalid_target_mapping", issue_codes: [] }];
  assert.throws(() => packScoutResult(unnamed, RUN), /names its failed checks/);

  const stray = structuredClone(scout);
  stray.quantitative_ledger.reviews = [{ ...review, failure_code: "invalid_model_response", issue_codes: ["invalid_target_quote"] }];
  assert.throws(() => packScoutResult(stray, RUN), /names its failed checks/);
});

/** A field retrieval investigated: it states a target and cites where. */
function searchableScout(): ScoutResponse {
  const result = structuredClone(scout);
  result.variables = [{
    name: "efficacy", description: "Protective efficacy", block_ids: [block.id],
    document_target: "Source text", document_spans: [{ quote: "Source text", block_ids: [block.id] }],
    definition_mode: "fixed", target_resolved: true, target_resolution_reason: "Stated in the document.",
    evidence_domain: "clinical", supplies_scope: "", entities: [], quantitative_target_ids: [],
    quantitative_statement_dispositions: [], quantitative_target_status: "not_applicable",
    quantitative_target_status_reason: "",
  }];
  result.assessments = [{
    attribute_ref: "efficacy", strength: "no_evidence", reason: "", doc_target: "Source text",
    doc_block_ids: [block.id], supporting_insight_ids: [], supporting_findings: [], failure_code: "",
  }];
  result.precedents = [{
    attribute_ref: "efficacy", precedent: "no_evidence", outcome: "no_evidence", reason: "",
    doc_block_ids: [block.id], coverage_insight_ids: [], outcome_insight_ids: [],
    supporting_insight_ids: [], supporting_findings: [], failure_code: "",
  }];
  return result;
}

test("Scout records no evidence apart from both a verdict and a failure", () => {
  // `no_evidence` is set by code when nothing retrieved reached a field: no call, so no
  // failure code, and nothing to cite. Read as `unknown` it would claim evidence was shown.
  const recorded = searchableScout();
  assert.deepEqual(unpackScoutResult(packScoutResult(recorded, RUN)), recorded);

  const coded = searchableScout();
  coded.assessments[0].failure_code = "provider_error";
  assert.throws(() => packScoutResult(coded, RUN), /a verdict but carries a failure code/);

  const cited = searchableScout();
  cited.precedents[0].supporting_findings = [{
    url: "https://example.org/a", title: "A", query: "q", retrieved_at: "2026-01-01T00:00:00Z",
    excerpt: "", published_at: null, source: "pubmed",
  }];
  assert.throws(() => packScoutResult(cited, RUN), /no_evidence .* cites evidence/);

  const halved = searchableScout();
  halved.precedents[0].outcome = "unknown";
  assert.throws(() => packScoutResult(halved, RUN), /both precedent axes or neither/);
});

test("every field retrieval investigated has one grounding and one precedent", () => {
  // A finished run judges, records no evidence for, or records the failure of every
  // searchable field, so none can be read as one the run never considered.
  const ungrounded = searchableScout();
  ungrounded.assessments = [];
  assert.throws(() => packScoutResult(ungrounded, RUN), /every searchable field needs one evidence assessment/);

  const doubled = searchableScout();
  doubled.precedents.push(structuredClone(doubled.precedents[0]));
  assert.throws(() => packScoutResult(doubled, RUN), /one precedent signal/);

  const stray = searchableScout();
  stray.variables[0].document_spans = [];
  assert.throws(() => packScoutResult(stray, RUN), /every searchable field/);
});

/** `searchableScout()` with its one field left out of search at target review. */
function unsearchedScout(): ScoutResponse {
  const result = searchableScout();
  result.not_searched_fields = ["efficacy"];
  result.assessments[0].strength = "not_searched";
  result.precedents[0].precedent = "not_searched";
  result.precedents[0].outcome = "not_searched";
  // Its numeric target was never calibrated, and nothing was retrieved for it.
  result.conformity = [];
  result.development_landscape = [];
  return result;
}

test("a field left out at review is not_searched on both records, and only that field", () => {
  const recorded = unsearchedScout();
  assert.deepEqual(unpackScoutResult(packScoutResult(recorded, RUN)), recorded);

  const unselected = unsearchedScout();
  unselected.not_searched_fields = [];
  assert.throws(() => packScoutResult(unselected, RUN), /not_searched exactly when/);

  const judged = searchableScout();
  judged.not_searched_fields = ["efficacy"];
  assert.throws(() => packScoutResult(judged, RUN), /not_searched exactly when/);

  const unknown = unsearchedScout();
  unknown.not_searched_fields = ["efficacy", "cogs"];
  assert.throws(() => packScoutResult(unknown, RUN), /not a searchable field/);

  const coded = unsearchedScout();
  coded.assessments[0].failure_code = "provider_error";
  assert.throws(() => packScoutResult(coded, RUN), /a verdict but carries a failure code/);

  const halved = unsearchedScout();
  halved.precedents[0].outcome = "no_evidence";
  assert.throws(() => packScoutResult(halved, RUN), /both precedent axes or neither/);
});

test("a field left out at review holds no evidence and no calibration", () => {
  const calibrated = unsearchedScout();
  calibrated.conformity = structuredClone(scout.conformity);
  assert.throws(() => packScoutResult(calibrated, RUN), /calibrat.*not searched/);

  const projected = unsearchedScout();
  projected.development_landscape = structuredClone(scout.development_landscape);
  assert.throws(() => packScoutResult(projected, RUN), /not searched/);
});

test("Scout states the scope its retrieval searched", () => {
  const unscoped = structuredClone(scout) as Partial<ScoutResponse>;
  delete unscoped.retrieval_scope;
  assert.throws(() => packScoutResult(unscoped as ScoutResponse, RUN), /retrieval scope/);

  const partial = structuredClone(scout);
  partial.retrieval_scope.entries.pop();
  assert.throws(() => packScoutResult(partial, RUN), /retrieval scope omits region/);

  const uncited = structuredClone(scout);
  uncited.retrieval_scope.entries[2] = { dimension: "region", value: "Kenya", provenance: "document", block_ids: [] };
  assert.throws(() => packScoutResult(uncited, RUN), /region.*cite/);

  const cited = structuredClone(scout);
  cited.retrieval_scope.entries[2] = { dimension: "region", value: "Kenya", provenance: "document", block_ids: [block.id] };
  assert.deepEqual(unpackScoutResult(packScoutResult(cited, RUN)), cited);
  cited.retrieval_scope.entries[2].block_ids = ["doc:missing"];
  assert.throws(() => packScoutResult(cited, RUN), /retrieval scope region/);
});

test("an identity layer that could not decide says so by code, and merged nothing", () => {
  const record = {
    layer: "projections" as const, scope: "", status: "not_reconciled" as const, items: 4, merged: 0,
    failure_code: "provider_error" as const, reason: "",
  };
  const unmerged = structuredClone(scout);
  unmerged.reconciliations = [record];
  assert.deepEqual(unpackScoutResult(packScoutResult(unmerged, RUN)), unmerged);

  const cases: [Partial<typeof record> | Record<string, unknown>, RegExp][] = [
    [{ failure_code: "" }, /carries a failure code/],
    [{ status: "reconciled", merged: 1 }, /carries a failure code/],
    [{ merged: 1 }, /merged nothing/],
    [{ layer: "documents" }, /unknown identity layer/],
    [{ items: 1 }, /two or more/],
    [{ layer: "insights", scope: "efficacy" }, /unknown field/],
    [{ scope: "efficacy" }, /document-wide/],
  ];
  for (const [change, error] of cases) {
    const malformed = structuredClone(scout);
    malformed.reconciliations = [{ ...record, ...change } as ScoutResponse["reconciliations"][number]];
    assert.throws(() => packScoutResult(malformed, RUN), error, JSON.stringify(change));
  }
});

test("a source is one record, however many links reached it", () => {
  // Distinct by record identity, not URL: two retrievals of one trial through two pages
  // are one source, and counting both would count it twice.
  const finding = {
    url: "https://example.org/trial", title: "Trial", query: "q", retrieved_at: "2026-01-01T00:00:00Z",
    excerpt: "", published_at: null, source: "clinicaltrials", record_key: "clinicaltrials:NCT00000001",
  };
  const twice = structuredClone(scout);
  twice.development_landscape[0].supporting_findings = [finding, { ...finding, url: "https://example.org/other" }];
  assert.throws(() => packScoutResult(twice, RUN), /cites one source twice/);

  const two = structuredClone(scout);
  two.development_landscape[0].supporting_findings = [finding, { ...finding, record_key: "clinicaltrials:NCT00000002" }];
  assert.doesNotThrow(() => packScoutResult(two, RUN));
});
