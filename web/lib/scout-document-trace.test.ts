import assert from "node:assert/strict";
import test from "node:test";

import type { ScoutResponse } from "./api.ts";
import { buildScoutDocumentAnnotations } from "./scout-document-trace.ts";

function slot(value = ""): {
  state: "specified" | "not_specified";
  value: string;
  other: string;
} {
  return value
    ? { state: "specified", value, other: "" }
    : { state: "not_specified", value: "", other: "" };
}

const result = {
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
    reason: "The document concerns malaria.",
    doc_block_ids: ["document/b-0001"],
  },
  quantitative_ledger: {
    status: "complete",
    reason: "One target was retained.",
    block_ids: ["document/b-0001"],
    reviews: [],
    targets: [
      {
        id: "qt-1",
        expression: {
          kind: "bound",
          unit: "%",
          value: 80,
          lower: null,
          upper: null,
          comparator: ">",
        },
        role: "optimal",
        quote: "Target efficacy >80% at 12 months.",
        doc_block_ids: ["document/b-0001"],
        field_links: [
          {
            attribute_ref: "vaccine.efficacy",
            relation: "defines",
            reason: "The field owns the target.",
          },
        ],
        semantic_profile: {
          measure: slot("protective efficacy"),
          endpoint: slot("clinical malaria"),
          intervention: slot("malaria vaccine"),
          population: slot(),
          regimen: slot(),
          time_horizon: slot("12 months"),
          statistic: slot("vaccine efficacy"),
          conditions: slot(),
        },
        comparison_contract: Object.fromEntries(
          [
            "measure",
            "endpoint",
            "intervention",
            "population",
            "regimen",
            "time_horizon",
            "statistic",
            "conditions",
          ].map((key) => [key, { mode: "compatible", scope: "Direct comparators", reason: "Compatible." }]),
        ),
        semantic_provenance: Object.fromEntries(
          [
            "measure",
            "endpoint",
            "intervention",
            "population",
            "regimen",
            "time_horizon",
            "statistic",
            "conditions",
          ].map((key) => [key, []]),
        ),
        provenance_spans: [
          {
            quote: "Target efficacy >80% at 12 months.",
            block_ids: ["document/b-0001"],
          },
        ],
        ai_recommendation: "confirm",
        ai_review_reason: "Explicit target.",
        review_status: "approved",
      },
    ],
  },
  variables: [
    {
      name: "vaccine.efficacy",
      description: "Protective efficacy.",
      block_ids: ["document/b-0001"],
      document_target: "Target efficacy >80% at 12 months.",
      document_spans: [
        {
          quote: "Target efficacy >80% at 12 months.",
          block_ids: ["document/b-0001"],
        },
      ],
      definition_mode: "fixed",
      target_resolved: true,
      target_resolution_reason: "Bound to an exact passage.",
      evidence_domain: "clinical",
      entities: [],
      quantitative_target_ids: ["qt-1"],
      quantitative_statement_dispositions: [],
      quantitative_target_status: "present",
      quantitative_target_status_reason: "One target.",
    },
  ],
  matches: [
    {
      insight: {
        id: "insight-1",
        statement: "A comparator reported 55% efficacy.",
        query: "malaria efficacy",
        supporting_findings: [],
        org: "bmgf",
        source_type: "itpp",
        intervention_class: "vaccine",
        indication: "malaria",
        attribute_ref: "vaccine.efficacy",
      },
      relation: "contradicts",
      reason: "The observed value is below the target.",
      doc_block_ids: ["document/b-0001"],
    },
    {
      insight: {
        statement: "No lineage should omit this match.",
        query: "irrelevant",
        supporting_findings: [],
        org: "bmgf",
        source_type: "itpp",
        intervention_class: "vaccine",
        indication: "malaria",
        attribute_ref: "vaccine.efficacy",
      },
      relation: "unrelated",
      reason: "No document lineage.",
      doc_block_ids: [],
    },
  ],
  assessments: [
    {
      attribute_ref: "vaccine.efficacy",
      strength: "partial",
      reason: "Direct evidence is limited.",
      doc_target: "Target efficacy >80% at 12 months.",
      doc_block_ids: ["document/b-0001"],
      supporting_insight_ids: ["insight-1"],
      supporting_findings: [],
    },
  ],
  conformity: [
    {
      attribute_refs: ["vaccine.efficacy", "vaccine.clinical_endpoint"],
      target_id: "qt-1",
      target_role: "optimal",
      target_value: 80,
      comparator: ">",
      unit: "%",
      target_label: "Target efficacy >80%",
      target_quote: "Target efficacy >80% at 12 months.",
      target_meeting_count: 0,
      target_meeting_rate: 0,
      verdict: "No admitted comparator met the target.",
      benchmark_count: 1,
      benchmark_minimum: 55,
      benchmark_maximum: 55,
      benchmark_mean: 55,
      benchmark_median: 55,
      benchmark_lower_quartile: 55,
      benchmark_upper_quartile: 55,
      benchmark_standard_deviation: 0,
      target_percentile: 100,
      ambition_percentile: 100,
      calibration_status: "limited",
      doc_block_ids: ["document/b-0001"],
      measurements: [],
      excluded_measurements: [],
      source_dispositions: [],
    },
  ],
  precedents: [
    {
      attribute_ref: "vaccine.efficacy",
      precedent: "direct",
      outcome: "mixed",
      reason: "Direct programs had mixed outcomes.",
      doc_block_ids: ["document/b-0001"],
      coverage_insight_ids: ["insight-1"],
      outcome_insight_ids: ["insight-1"],
      supporting_insight_ids: ["insight-1"],
      supporting_findings: [],
    },
  ],
  development_landscape: [],
  safety_observations: [],
  stats: {
    queries: 1,
    findings: 1,
    unique_findings: 1,
    insights: 1,
    matches: 1,
    assessments: 1,
  },
  blocks: [],
} as unknown as ScoutResponse;

test("projects every Scout result axis without inventing exact spans", () => {
  const annotations = buildScoutDocumentAnnotations(result);

  assert.deepEqual(
    annotations.map((annotation) => annotation.kind),
    [
      "field",
      "quantitative_target",
      "relationship",
      "grounding",
      "calibration",
      "precedent",
    ],
  );
  assert.deepEqual(annotations[0].spans, [{
    quote: "Target efficacy >80% at 12 months.",
    blockIds: ["document/b-0001"],
  }]);
  assert.deepEqual(annotations[1].spans, [{
    quote: "Target efficacy >80% at 12 months.",
    blockIds: ["document/b-0001"],
  }]);
  for (const annotation of annotations.slice(2)) {
    assert.deepEqual(annotation.spans, []);
  }
});

test("retains multi-field calibration linkage in one immutable annotation", () => {
  const annotations = buildScoutDocumentAnnotations(result);
  const calibration = annotations.find((annotation) => annotation.kind === "calibration");

  assert.deepEqual(calibration?.sourceRef, {
    type: "calibration",
    targetId: "qt-1",
    attributeRefs: ["vaccine.efficacy", "vaccine.clinical_endpoint"],
  });
  assert.equal(calibration?.summary, "No admitted comparator met the target.");
});

test("preserves quantitative quote-to-block provenance without a cross-product", () => {
  const multiSpan = structuredClone(result);
  const target = multiSpan.quantitative_ledger!.targets[0];
  target.doc_block_ids = ["document/b-0001", "document/b-0002"];
  target.provenance_spans = [
    { quote: "Optimal target is 80%.", block_ids: ["document/b-0001"] },
    { quote: "Threshold target is 60%.", block_ids: ["document/b-0002"] },
  ];

  const quantitative = buildScoutDocumentAnnotations(multiSpan).find(
    (annotation) => annotation.kind === "quantitative_target",
  );

  assert.deepEqual(quantitative?.spans, [
    { quote: "Optimal target is 80%.", blockIds: ["document/b-0001"] },
    { quote: "Threshold target is 60%.", blockIds: ["document/b-0002"] },
  ]);
});

test("produces stable IDs and does not mutate the Scout result", () => {
  const before = structuredClone(result);
  const first = buildScoutDocumentAnnotations(result);
  const second = buildScoutDocumentAnnotations(result);

  assert.deepEqual(first.map((annotation) => annotation.id), second.map((annotation) => annotation.id));
  assert.deepEqual(result, before);
  assert.equal(first.some((annotation) => annotation.summary === "No document lineage."), false);
});

test("Scout claims spans and blocks only, never anchors or block emphasis", () => {
  // The shared contract grew `emphasis` and `displayAnchorBlockId` for Inspector,
  // whose findings can describe absent content. Scout's every layer is guarded by
  // document lineage, so neither field applies here. If this fails, Scout has
  // started rendering Inspector's whole-block tint and dashed gap markers.
  const annotations = buildScoutDocumentAnnotations(result);

  assert.ok(annotations.length > 0, "fixture produced no annotations to check");
  assert.deepEqual(
    annotations.filter((annotation) => annotation.emphasis !== undefined).map((a) => a.id),
    [],
    "Scout has no grading scale, so no annotation carries a block tone",
  );
  assert.deepEqual(
    annotations.filter((annotation) => annotation.displayAnchorBlockId !== undefined).map((a) => a.id),
    [],
    "Scout never places an annotation without provenance",
  );
  assert.deepEqual(
    annotations.filter((annotation) => annotation.blockIds.length === 0).map((a) => a.id),
    [],
    "every Scout annotation cites at least one retained block",
  );
});
