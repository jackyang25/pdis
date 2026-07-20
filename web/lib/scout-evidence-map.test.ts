import assert from "node:assert/strict";
import test from "node:test";

import type { ScoutResponse } from "./api.ts";
import { buildScoutEvidenceMap } from "./scout-evidence-map.ts";

const result = {
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
  variables: [
    {
      name: "clinical_efficacy",
      description: "Protective efficacy against clinical disease.",
      block_ids: ["document/b-0007"],
      document_target: "The vaccine target is at least 75% efficacy.",
      definition_mode: "fixed",
      target_resolved: true,
      evidence_domain: "clinical",
      entities: [],
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
  safety_signals: [],
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
