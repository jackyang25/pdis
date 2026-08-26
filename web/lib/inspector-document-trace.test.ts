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
  Assessment,
  ContentBlock,
  InspectionResult,
  SectionAssessment,
  Verdict,
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
  verdict: Verdict,
  citedBlockIds: string[] = [],
  overrides: Partial<Assessment> = {},
): Assessment {
  const sound = verdict === "specified" || verdict === "not_applicable";
  return {
    id: `${overrides.section_name ?? "Efficacy"}|${overrides.variable_name ?? ""}`,
    verdict,
    statement: sound ? "" : `A ${verdict} problem.`,
    section_name: "Efficacy",
    variable_name: null,
    optional: false,
    cited_block_ids: citedBlockIds,
    rank: 0,
    ...overrides,
  };
}

/** A unit is its assessment now, so this only names the arguments. */
function unit(
  variableName: string | null,
  verdict: Verdict,
  citedBlockIds: string[] = [],
  optional = false,
): Assessment {
  return finding(verdict, citedBlockIds, { variable_name: variableName, optional });
}

function section(
  name: string,
  mappedBlockIds: string[],
  units: Assessment[],
  isPresent = true,
): SectionAssessment {
  return {
    section_name: name,
    is_present: isPresent,
    mapped_block_ids: mappedBlockIds,
    units,
    verdict_counts: {} as Record<Verdict, number>,
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

test("projects one annotation per unit, not one per question asked", () => {
  const annotations = buildInspectorDocumentAnnotations(result({
    blocks: BLOCKS,
    sections: [
      section("Efficacy", ["b-1", "b-2"], [
        finding("placeholder", ["b-2"], { variable_name: "Seroconversion rate", rank: 0 }),
        finding("vague", ["b-2"], { variable_name: "Formulation", rank: 1 }),
      ]),
    ],
  }));

  assert.deepEqual(
    annotations.map((item) => [item.kind, item.statusLabel]),
    [
      ["placeholder", "Placeholder"],
      ["vague", "Vague"],
    ],
  );
});

test("each unit is placed on its own citations, never a sibling's", () => {
  const annotations = buildInspectorDocumentAnnotations(result({
    blocks: BLOCKS,
    sections: [
      section("Efficacy", ["b-1", "b-2"], [
        finding("placeholder", ["b-1"], { variable_name: "Seroconversion rate", rank: 0 }),
        finding("vague", ["b-1", "b-2"], { variable_name: "Formulation", rank: 1 }),
      ]),
    ],
  }));

  const byKind = new Map(annotations.map((item) => [item.kind, item.blockIds]));
  assert.deepEqual(byKind.get("placeholder"), ["b-1"]);
  assert.deepEqual(byKind.get("vague"), ["b-1", "b-2"]);
});

test("tone follows the verdict, so there is no second table to keep in step", () => {
  // Read off the one axis: the verdicts that leave the requirement unsatisfied read as
  // danger, the two that only weaken it read as caution. There used to be a `level`
  // field carrying this, which was a lookup on the verdict and nothing else.
  const cases: Array<[Verdict, string]> = [
    ["not_present", "danger"],
    ["placeholder", "danger"],
    ["insufficient", "danger"],
    ["vague", "warning"],
  ];
  for (const [verdict, tone] of cases) {
    const cited = verdict === "not_present" ? [] : ["b-2"];
    const annotations = buildInspectorDocumentAnnotations(result({
      blocks: BLOCKS,
      sections: [
        section("Efficacy", ["b-1", "b-2"], [
          finding(verdict, cited, { variable_name: "V" }),
        ]),
      ],
    }));
    assert.equal(annotations.length, 1, `${verdict} should emit once`);
    assert.equal(annotations[0].emphasis?.tone, tone, verdict);
  }
});

test("a met unit contributes nothing, because there is no finding to place", () => {
  const annotations = buildInspectorDocumentAnnotations(result({
    blocks: BLOCKS,
    sections: [section("Efficacy", ["b-1", "b-2"], [finding("specified", ["b-2"], { variable_name: "V" })])],
  }));

  assert.deepEqual(annotations, []);
});

test("an absence the rubric accepts is not shown in the gutter", () => {
  // The one rule that keeps the trace and the worklist in agreement: both exclude it by
  // reading the same list. `not_applicable` is the verdict for it now - the rubric
  // accepts the absence, so the unit is not work. It used to be `missing` on a unit
  // whose `optional` flag turned it into a `not_applicable` status, which is the two
  // axes doing one job between them.
  const annotations = buildInspectorDocumentAnnotations(result({
    blocks: BLOCKS,
    sections: [
      section("Efficacy", ["b-1", "b-2"], [
        finding("not_applicable", [], { variable_name: "Companion test", optional: true }),
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
        finding("not_present", [], { variable_name: "Duration of protection" }),
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
        finding("not_present", [], {
          section_name: "Manufacturing",
          variable_name: "Fill-finish capacity",
        }),
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
        finding("vague", ["b-3"], { section_name: "Safety" }),
      ]),
    ],
  }));

  assert.equal(annotations.length, 1);
  assert.equal(annotations[0].title, "Safety");
  assert.deepEqual(annotations[0].blockIds, ["b-3"]);
  assert.equal(annotations[0].displayAnchorBlockId, undefined, "a cited finding is placed");
});

test("the summary is the unit's own statement", () => {
  // There used to be a second sentence beside it - a `recommendation` restating the
  // statement as an imperative - and the summary had to choose between them.
  const annotations = buildInspectorDocumentAnnotations(result({
    blocks: BLOCKS,
    sections: [
      section("Safety", ["b-3"], [
        finding("vague", ["b-3"], {
          section_name: "Safety",
          statement: "No units are given.",
        }),
      ]),
    ],
  }));

  assert.equal(annotations[0].summary, "No units are given.");
});

test("a conflict is danger, keeps its lineage, and titles itself from it", () => {
  const annotations = buildInspectorDocumentAnnotations(result({
    blocks: BLOCKS,
    sections: [
      section("Efficacy", ["b-1", "b-2"], [finding("specified", ["b-2"], { variable_name: "V" })]),
      section("Safety", ["b-3"], [finding("specified", ["b-2"], { variable_name: null })]),
    ],
    document_findings: [
      finding("section_conflict", ["b-2", "b-3"], {
        id: "conflict|0",
        section_name: null,
        statement: "Efficacy targets 60% while Safety assumes 90%.",
      }),
    ],
  }));

  assert.equal(annotations.length, 1);
  assert.equal(annotations[0].kind, "section_conflict");
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
        finding("vague", ["b-2"], { variable_name: "Seroconversion rate", rank: 2 }),
        finding("not_present", [], { variable_name: "Duration of protection", rank: 1 }),
      ]),
    ],
  }));

  assert.deepEqual(annotations.map((item) => item.kind), ["not_present", "vague"]);
});

test("the input result is not mutated and projection is deterministic", () => {
  const input = result({
    blocks: BLOCKS,
    sections: [
      section("Efficacy", ["b-1", "b-2"], [
        finding("vague", ["b-2"], { variable_name: "Seroconversion rate", rank: 1 }),
        finding("not_present", [], { variable_name: "Duration of protection", rank: 0 }),
      ]),
    ],
  });
  const snapshot = structuredClone(input);

  const first = buildInspectorDocumentAnnotations(input);
  const second = buildInspectorDocumentAnnotations(input);

  assert.deepEqual(input, snapshot, "the projection must not mutate its input");
  assert.deepEqual(first, second);
});
