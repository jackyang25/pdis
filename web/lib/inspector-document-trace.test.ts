/**
 * The Inspector trace adapter is a projection, so these tests assert it reports
 * exactly what the result already says and derives nothing the service has not
 * already resolved.
 *
 * The shape this replaced looped three dimensions over every unit, so one defect
 * could produce three gutter markers and two were usually empty. One finding is now
 * one annotation, drawn from the same worklist the findings list shows, so the
 * gutter and the list cannot disagree about what counts as work.
 */

import assert from "node:assert/strict";
import test from "node:test";

import type {
  ContentBlock,
  FindingReason,
  InspectionResult,
  RubricFinding,
  SectionAssessment,
  UnitAssessment,
  UnitStatus,
} from "./api.ts";
import { buildDocumentTrace } from "./document-trace.ts";
import { buildInspectorDocumentAnnotations } from "./inspector-document-trace.ts";

function block(
  id: string,
  ordinal: number,
  content: string,
  sectionLabel: string | null = null,
): ContentBlock {
  return {
    id,
    doc_id: "plan",
    ordinal,
    block_type: "paragraph",
    content,
    heading_stack: [],
    section_label: sectionLabel,
    structural_meta: {},
    style_hint: {},
  };
}

function finding(
  reason: FindingReason,
  citedBlockIds: string[] = [],
  overrides: Partial<RubricFinding> = {},
): RubricFinding {
  return {
    id: `${overrides.section_name ?? "Efficacy"}|${overrides.variable_name ?? ""}|${reason}`,
    reason,
    statement: `A ${reason} problem.`,
    recommendation: "Do the thing.",
    section_name: "Efficacy",
    variable_name: null,
    cited_block_ids: citedBlockIds,
    rank: 0,
    level: reason === "off_template" || reason === "unclear" ? "could_be_stronger" : "not_met",
    ...overrides,
  };
}

function unit(
  variableName: string | null,
  status: UnitStatus,
  findings: RubricFinding[],
  optional = false,
): UnitAssessment {
  return { variable_name: variableName, optional, findings, status };
}

function section(
  name: string,
  mappedBlockIds: string[],
  units: UnitAssessment[],
  isPresent = true,
): SectionAssessment {
  return {
    section_name: name,
    is_present: isPresent,
    mapped_block_ids: mappedBlockIds,
    units,
    status_counts: { met: 0, could_be_stronger: 0, not_met: 0, not_applicable: 0 },
  };
}

function result(overrides: Partial<InspectionResult> = {}): InspectionResult {
  return {
    doc_id: "plan",
    sections: [],
    document_findings: [],
    consistency_status: "complete",
    assessment_status: "complete",
    org: "bmgf",
    source_type: "itpp",
    intervention_class: "vaccine",
    indication: "malaria",
    blocks: [],
    ...overrides,
  };
}

const BLOCKS = [
  block("b-1", 1, "Efficacy", "Efficacy"),
  block("b-2", 2, "Minimum: 60% seroconversion", "Efficacy"),
  block("b-3", 3, "Safety", "Safety"),
];

test("projects one annotation per finding, not one per question asked", () => {
  const annotations = buildInspectorDocumentAnnotations(result({
    blocks: BLOCKS,
    sections: [
      section("Efficacy", ["b-1", "b-2"], [
        unit("Seroconversion rate", "could_be_stronger", [
          finding("off_template", ["b-2"], { variable_name: "Seroconversion rate", rank: 0 }),
          finding("unclear", ["b-2"], { variable_name: "Seroconversion rate", rank: 1 }),
        ]),
      ]),
    ],
  }));

  assert.deepEqual(
    annotations.map((item) => [item.kind, item.statusLabel]),
    [
      ["off_template", "Off template"],
      ["unclear", "Vague"],
    ],
  );
});

test("each finding is placed on its own citations, never a sibling's", () => {
  const annotations = buildInspectorDocumentAnnotations(result({
    blocks: BLOCKS,
    sections: [
      section("Efficacy", ["b-1", "b-2"], [
        unit("Seroconversion rate", "could_be_stronger", [
          finding("off_template", ["b-1"], { variable_name: "Seroconversion rate", rank: 0 }),
          finding("unclear", ["b-1", "b-2"], { variable_name: "Seroconversion rate", rank: 1 }),
        ]),
      ]),
    ],
  }));

  const byKind = new Map(annotations.map((item) => [item.kind, item.blockIds]));
  assert.deepEqual(byKind.get("off_template"), ["b-1"]);
  assert.deepEqual(byKind.get("unclear"), ["b-1", "b-2"]);
});

test("tone follows the level, so there is no second table to keep in step", () => {
  const cases: Array<[FindingReason, string]> = [
    ["missing", "danger"],
    ["placeholder", "danger"],
    ["unmet", "danger"],
    ["off_template", "caution"],
    ["unclear", "caution"],
  ];
  for (const [reason, tone] of cases) {
    const cited = reason === "missing" ? [] : ["b-2"];
    const annotations = buildInspectorDocumentAnnotations(result({
      blocks: BLOCKS,
      sections: [
        section("Efficacy", ["b-1", "b-2"], [
          unit("V", reason === "off_template" || reason === "unclear" ? "could_be_stronger" : "not_met", [
            finding(reason, cited, { variable_name: "V" }),
          ]),
        ]),
      ],
    }));
    assert.equal(annotations.length, 1, `${reason} should emit once`);
    assert.equal(annotations[0].emphasis?.tone, tone, reason);
  }
});

test("a met unit contributes nothing, because there is no finding to place", () => {
  const annotations = buildInspectorDocumentAnnotations(result({
    blocks: BLOCKS,
    sections: [section("Efficacy", ["b-1", "b-2"], [unit("V", "met", [])])],
  }));

  assert.deepEqual(annotations, []);
});

test("an absence the rubric accepts is not shown in the gutter", () => {
  // The one rule that keeps the trace and the findings list in agreement: the unit
  // keeps its finding so it can explain itself, and both views exclude it by
  // reading the same worklist.
  const annotations = buildInspectorDocumentAnnotations(result({
    blocks: BLOCKS,
    sections: [
      section("Efficacy", ["b-1", "b-2"], [
        unit("Companion test", "not_applicable", [
          finding("missing", [], { variable_name: "Companion test" }),
        ], true),
      ]),
    ],
  }));

  assert.deepEqual(annotations, []);
});

test("an absent unit cites nothing and anchors to its section's last block", () => {
  const annotations = buildInspectorDocumentAnnotations(result({
    blocks: BLOCKS,
    sections: [
      section("Efficacy", ["b-1", "b-2"], [
        unit("Duration of protection", "not_met", [
          finding("missing", [], { variable_name: "Duration of protection" }),
        ]),
      ]),
    ],
  }));

  assert.equal(annotations.length, 1, "one absence is one finding");
  assert.deepEqual(annotations[0].blockIds, [], "an absence cites nothing");
  assert.equal(annotations[0].displayAnchorBlockId, "b-2", "last mapped block");
  assert.equal(annotations[0].statusLabel, "Not present");
});

test("an unwritten section maps no blocks, so its finding has no anchor", () => {
  const annotations = buildInspectorDocumentAnnotations(result({
    blocks: BLOCKS,
    sections: [
      section("Manufacturing", [], [
        unit("Fill-finish capacity", "not_met", [
          finding("missing", [], {
            section_name: "Manufacturing",
            variable_name: "Fill-finish capacity",
          }),
        ]),
      ], false),
    ],
  }));

  assert.equal(annotations.length, 1);
  assert.equal(annotations[0].displayAnchorBlockId, undefined);
  const trace = buildDocumentTrace(BLOCKS, annotations);
  assert.deepEqual(trace.unplacedAnnotationIds, [annotations[0].id]);
});

test("a prose section's finding is titled and scoped by the section itself", () => {
  const annotations = buildInspectorDocumentAnnotations(result({
    blocks: BLOCKS,
    sections: [
      section("Safety", ["b-3"], [
        unit(null, "could_be_stronger", [
          finding("unclear", ["b-3"], { section_name: "Safety" }),
        ]),
      ]),
    ],
  }));

  assert.equal(annotations.length, 1);
  assert.equal(annotations[0].title, "Safety");
  assert.deepEqual(annotations[0].blockIds, ["b-3"]);
  assert.equal(annotations[0].displayAnchorBlockId, undefined, "a cited finding is placed");
});

test("the summary is the finding's own statement, never its recommendation", () => {
  const annotations = buildInspectorDocumentAnnotations(result({
    blocks: BLOCKS,
    sections: [
      section("Safety", ["b-3"], [
        unit(null, "could_be_stronger", [
          finding("unclear", ["b-3"], {
            section_name: "Safety",
            statement: "No units are given.",
            recommendation: "State the value with units.",
          }),
        ]),
      ]),
    ],
  }));

  assert.equal(annotations[0].summary, "No units are given.");
});

test("a conflict is danger, keeps its lineage, and titles itself from it", () => {
  const annotations = buildInspectorDocumentAnnotations(result({
    blocks: BLOCKS,
    sections: [
      section("Efficacy", ["b-1", "b-2"], [unit("V", "met", [])]),
      section("Safety", ["b-3"], [unit(null, "met", [])]),
    ],
    document_findings: [
      finding("conflicting", ["b-2", "b-3"], {
        id: "conflict|0",
        section_name: null,
        statement: "Efficacy targets 60% while Safety assumes 90%.",
      }),
    ],
  }));

  assert.equal(annotations.length, 1);
  assert.equal(annotations[0].kind, "conflicting");
  // The sections involved are resolved from the citations rather than stored, so
  // the title cannot name a section the finding does not actually cite.
  assert.equal(annotations[0].title, "Efficacy ↔ Safety");
  assert.deepEqual(annotations[0].blockIds, ["b-2", "b-3"]);
  assert.equal(annotations[0].emphasis?.tone, "danger");
});

test("annotations follow the order the result assigned", () => {
  const annotations = buildInspectorDocumentAnnotations(result({
    blocks: BLOCKS,
    sections: [
      section("Efficacy", ["b-1", "b-2"], [
        unit("Seroconversion rate", "could_be_stronger", [
          finding("unclear", ["b-2"], { variable_name: "Seroconversion rate", rank: 2 }),
        ]),
        unit("Duration of protection", "not_met", [
          finding("missing", [], { variable_name: "Duration of protection", rank: 1 }),
        ]),
      ]),
    ],
  }));

  assert.deepEqual(annotations.map((item) => item.kind), ["missing", "unclear"]);
});

test("the input result is not mutated and projection is deterministic", () => {
  const input = result({
    blocks: BLOCKS,
    sections: [
      section("Efficacy", ["b-1", "b-2"], [
        unit("Seroconversion rate", "could_be_stronger", [
          finding("unclear", ["b-2"], { variable_name: "Seroconversion rate", rank: 1 }),
        ]),
        unit("Duration of protection", "not_met", [
          finding("missing", [], { variable_name: "Duration of protection", rank: 0 }),
        ]),
      ]),
    ],
  });
  const snapshot = structuredClone(input);

  const first = buildInspectorDocumentAnnotations(input);
  const second = buildInspectorDocumentAnnotations(input);

  assert.deepEqual(input, snapshot, "the projection must not mutate its input");
  assert.deepEqual(first, second);
});
