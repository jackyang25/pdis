import assert from "node:assert/strict";
import test from "node:test";

import type { Conformity, ScoutResponse } from "./api.ts";
import { buildScoutEvidenceMap } from "./scout-evidence-map.ts";

const result = {
  phase: "final" as const,
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
    doc_block_ids: ["document/b-0007"],
  },
  quantitative_ledger: {
    status: "not_applicable",
    reason: "No document statements were mapped.",
    block_ids: [],
    reviews: [],
    targets: [],
  },
  variables: [
    {
      name: "clinical_efficacy",
      description: "Protective efficacy against clinical disease.",
      block_ids: ["document/b-0007"],
      document_target: "The vaccine target is at least 75% efficacy.",
      document_spans: [{
        quote: "The vaccine target is at least 75% efficacy.",
        block_ids: ["document/b-0007"],
      }],
      definition_mode: "fixed",
      target_resolved: true,
      target_resolution_reason: "Resolved from exact document spans.",
      evidence_domain: "clinical",
      entities: [],
      quantitative_target_ids: [],
      quantitative_statement_dispositions: [],
      quantitative_target_status: "not_applicable" as const,
      quantitative_target_status_reason: "No numeric target is stated.",
    },
  ],
  matches: [
    {
      insight: {
        id: "i-efficacy",
        statement: "A Phase 3 trial reported 70% efficacy.",
        query: "malaria vaccine phase 3 efficacy",
        supporting_findings: [
          {
            url: "https://example.test/trial",
            title: "Phase 3 trial",
            query: "malaria vaccine phase 3 efficacy",
            retrieved_at: "2026-07-19T00:00:00Z",
            excerpt: "The trial reported 70% efficacy.",
            published_at: null,
            source: "pubmed",
          },
        ],
        org: "bmgf",
        source_type: "itpp",
        intervention_class: "vaccine",
        indication: "malaria",
        attribute_ref: "clinical_efficacy",
      },
      relation: "contradicts",
      reason: "The observed efficacy is below the document target.",
      doc_block_ids: ["document/b-0007"],
    },
  ],
  assessments: [
    {
      attribute_ref: "clinical_efficacy",
      strength: "partial",
      reason: "One direct trial was found.",
      // Deliberately stale: the graph must never use a reasoning-layer copy as
      // its canonical target.
      doc_target: "A stale assessment copy.",
      doc_block_ids: ["document/b-9999"],
      supporting_insight_ids: ["i-efficacy"],
      supporting_findings: [],
    },
  ],
  conformity: [],
  precedents: [],
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
} satisfies ScoutResponse;

test("uses the canonical target and attaches evidence relations to it", () => {
  const projection = buildScoutEvidenceMap(result, "clinical_efficacy");
  const document = projection.nodes.find(
    (node) => node.id === "document:clinical_efficacy",
  );

  assert.equal(document?.summary, "The vaccine target is at least 75% efficacy.");
  assert.deepEqual(document?.blockIds, ["document/b-0007"]);
  assert.ok(
    projection.edges.some(
      (edge) =>
        edge.source === "field:clinical_efficacy" &&
        edge.target === "document:clinical_efficacy" &&
        edge.kind === "has_target",
    ),
  );
  assert.ok(
    projection.edges.some(
      (edge) =>
        edge.source === "document:clinical_efficacy" &&
        edge.target === "insight:i-efficacy" &&
        edge.kind === "contradicts",
    ),
  );
  const nodeIds = new Set(projection.nodes.map((node) => node.id));
  for (const edge of projection.edges) {
    assert.ok(nodeIds.has(edge.source), `missing edge source ${edge.source}`);
    assert.ok(nodeIds.has(edge.target), `missing edge target ${edge.target}`);
  }
});

test("all mode maps every cited insight and source for the selected field", () => {
  const expanded = structuredClone(result) as ScoutResponse;
  expanded.matches.push({
    ...expanded.matches[0],
    insight: {
      ...expanded.matches[0].insight,
      id: "i-second",
      statement: "A second study reported durable protection.",
      supporting_findings: [
        {
          ...expanded.matches[0].insight.supporting_findings[0],
          url: "https://example.test/second",
          title: "Second study",
        },
      ],
    },
    relation: "confirms",
  });

  const focused = buildScoutEvidenceMap(expanded, "clinical_efficacy", {
    insights: 1,
    sources: 1,
  });
  const all = buildScoutEvidenceMap(expanded, "clinical_efficacy", { mode: "all" });

  assert.equal(focused.shownInsights, 1);
  assert.equal(focused.shownSources, 1);
  assert.equal(all.shownInsights, 2);
  assert.equal(all.shownSources, 2);
});

// A field can own several numeric targets (a threshold plus an optimal, say),
// and calibration produces one record per target. The field signal must
// describe the whole field, not whichever record happens to come first.
const conformityFor = (
  targetId: string,
  over: Partial<Conformity>,
): Conformity => ({
  attribute_refs: ["clinical_efficacy"],
  target_id: targetId,
  target_role: "threshold",
  target_value: 75,
  comparator: ">=",
  unit: "%",
  target_label: "at least 75%",
  target_quote: "at least 75% efficacy",
  target_meeting_count: 0,
  target_meeting_rate: 0,
  verdict: "",
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
  measurements: [],
  excluded_measurements: [],
  source_dispositions: [],
  ...over,
});

const calibrationSignal = (response: ScoutResponse) =>
  buildScoutEvidenceMap(response, "clinical_efficacy")
    .nodes.find((node) => node.id === "field:clinical_efficacy")
    ?.signals?.find((signal) => signal.label === "Quantitative calibration");

test("field calibration reflects every numeric target the field owns", () => {
  const multi = structuredClone(result) as ScoutResponse;
  multi.conformity = [
    conformityFor("t-threshold", { benchmark_count: 0, target_meeting_count: 0 }),
    conformityFor("t-optimal", {
      target_role: "optimal",
      target_value: 90,
      target_label: "ideally 90%",
      benchmark_count: 12,
      target_meeting_count: 5,
    }),
  ];

  // Counts aggregate; the meeting rate does not, because separate targets are
  // not calculation-compatible.
  assert.equal(calibrationSignal(multi)?.value, "12 comparators");
  // The per-target split belongs on the node's meta line, where it has room.
  const fieldNode = buildScoutEvidenceMap(multi, "clinical_efficacy").nodes.find(
    (node) => node.id === "field:clinical_efficacy",
  );
  assert.equal(fieldNode?.meta, "2 numeric targets · 1 insight");
});

test("field calibration keeps the meeting rate for a single numeric target", () => {
  const single = structuredClone(result) as ScoutResponse;
  single.conformity = [
    conformityFor("t-threshold", { benchmark_count: 12, target_meeting_count: 5 }),
  ];

  assert.equal(calibrationSignal(single)?.value, "5/12 meet target");
});

test("field calibration reports an empty cohort without hiding the targets", () => {
  const empty = structuredClone(result) as ScoutResponse;
  empty.conformity = [
    conformityFor("t-threshold", {}),
    conformityFor("t-optimal", { target_role: "optimal", target_value: 90 }),
  ];

  assert.equal(calibrationSignal(empty)?.value, "None admitted");
});

test("a measurement on any numeric target marks its insight as analysis-backed", () => {
  const multi = structuredClone(result) as ScoutResponse;
  // Two equally ranked matches. The later one is cited by the second target's
  // measurement, so the focused view must prefer it over pipeline order.
  multi.matches = [
    { ...multi.matches[0], relation: "extends", insight: { ...multi.matches[0].insight, id: "i-plain" } },
    { ...multi.matches[0], relation: "extends", insight: { ...multi.matches[0].insight, id: "i-calibrated" } },
  ];
  multi.conformity = [
    conformityFor("t-threshold", {}),
    conformityFor("t-optimal", {
      target_role: "optimal",
      benchmark_count: 1,
      measurements: [
        { insight_id: "i-calibrated" } as Conformity["measurements"][number],
      ],
    }),
  ];

  const focused = buildScoutEvidenceMap(multi, "clinical_efficacy", {
    insights: 1,
    sources: 1,
  });
  const insightIds = focused.nodes
    .filter((node) => node.kind === "insight")
    .map((node) => node.id);
  assert.deepEqual(insightIds, ["insight:i-calibrated"]);
});
