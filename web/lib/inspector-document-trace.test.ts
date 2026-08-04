/**
 * The Inspector trace adapter is a projection, so these tests assert it reports
 * exactly what the result already says and derives nothing the canonical layer
 * has not already resolved.
 */

import assert from "node:assert/strict";
import test from "node:test";

import type {
  ContentBlock,
  ContentStatus,
  DimensionVerdict,
  InspectionResult,
  SectionGrade,
  VariableGrade,
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

/** Lineage belongs to the dimension that cited it. */
function grade(
  value: DimensionVerdict,
  citedBlockIds: string[] = [],
  issues: string[] = [],
  recommendation = "",
) {
  return { verdict: value, issues, recommendation, cited_block_ids: citedBlockIds };
}

function dimensions(
  completeness: ReturnType<typeof grade>,
  adherence: ReturnType<typeof grade>,
  rigor: ReturnType<typeof grade>,
) {
  return { completeness, adherence, rigor };
}

function variable(
  name: string,
  contentStatus: ContentStatus,
  dims: ReturnType<typeof dimensions>,
): VariableGrade {
  return { variable_name: name, dimensions: dims, content_status: contentStatus };
}

function section(
  name: string,
  dims: ReturnType<typeof dimensions>,
  variables: VariableGrade[],
  mappedBlockIds: string[],
  isPresent = true,
): SectionGrade {
  return {
    section_name: name,
    is_present: isPresent,
    dimensions: dims,
    variable_grades: variables,
    mapped_block_ids: mappedBlockIds,
    gap_counts: { critical: 0, for_consideration: 0 },
  };
}

function result(overrides: Partial<InspectionResult> = {}): InspectionResult {
  return {
    doc_id: "plan",
    top_issues: [],
    section_grades: [],
    cross_section_findings: [],
    consistency_status: "complete",
    grading_status: "complete",
    org: "bmgf",
    source_type: "itpp",
    intervention_class: "vaccine",
    indication: "malaria",
    gap_counts: { critical: 0, for_consideration: 0 },
    blocks: [],
    ...overrides,
  };
}

const BLOCKS = [
  block("b-1", 1, "Efficacy", "Efficacy"),
  block("b-2", 2, "Minimum: 60% seroconversion", "Efficacy"),
  block("b-3", 3, "Safety", "Safety"),
];
const NA = dimensions(grade("not_applicable"), grade("not_applicable"), grade("not_applicable"));

test("projects one annotation per assessed variable dimension", () => {
  const annotations = buildInspectorDocumentAnnotations(result({
    blocks: BLOCKS,
    section_grades: [section(
      "Efficacy",
      dimensions(grade("for_consideration"), grade("for_consideration"), grade("for_consideration")),
      [variable("Seroconversion rate", "substantive", dimensions(
        grade("meets", ["b-2"]),
        grade("for_consideration", ["b-2"]),
        grade("critical", ["b-2"]),
      ))],
      ["b-1", "b-2"],
    )],
  }));

  assert.deepEqual(
    annotations.map((item) => [item.kind, item.statusLabel]),
    [
      ["completeness", "Meets"],
      ["adherence", "Consider"],
      ["rigor", "Critical"],
    ],
  );
});

test("each dimension is placed on its own citations, never a sibling's", () => {
  // The whole point of per-dimension lineage: rigor read a block completeness
  // did not, so a completeness verdict must not land on it.
  const annotations = buildInspectorDocumentAnnotations(result({
    blocks: BLOCKS,
    section_grades: [section(
      "Efficacy",
      dimensions(grade("meets"), grade("not_applicable"), grade("critical")),
      [variable("Seroconversion rate", "substantive", dimensions(
        grade("meets", ["b-2"]),
        grade("not_applicable"),
        grade("critical", ["b-1", "b-2"]),
      ))],
      ["b-1", "b-2"],
    )],
  }));

  const byKind = new Map(annotations.map((item) => [item.kind, item.blockIds]));
  assert.deepEqual(byKind.get("completeness"), ["b-2"]);
  assert.deepEqual(byKind.get("rigor"), ["b-1", "b-2"]);
});

test("maps every verdict to its tone and carries a readable badge", () => {
  const cases: Array<[DimensionVerdict, string, string]> = [
    ["meets", "neutral", "Meets"],
    ["for_consideration", "caution", "Consider"],
    ["critical", "danger", "Critical"],
  ];
  for (const [value, tone, badge] of cases) {
    const annotations = buildInspectorDocumentAnnotations(result({
      blocks: BLOCKS,
      section_grades: [section("Efficacy", NA, [
        variable("V", "substantive", dimensions(
          grade(value, ["b-2"]),
          grade("not_applicable"),
          grade("not_applicable"),
        )),
      ], ["b-1", "b-2"])],
    }));
    assert.equal(annotations.length, 1, `verdict ${value} should emit once`);
    assert.deepEqual(annotations[0].emphasis, { tone, badge });
  }
});

test("skips not_applicable dimensions because the rubric does not ask", () => {
  const annotations = buildInspectorDocumentAnnotations(result({
    blocks: BLOCKS,
    section_grades: [section("Efficacy", NA, [
      variable("V", "not_applicable", NA),
    ], ["b-1", "b-2"])],
  }));
  assert.deepEqual(annotations, []);
});

test("an absent variable cites nothing and anchors to its section's last block", () => {
  const annotations = buildInspectorDocumentAnnotations(result({
    blocks: BLOCKS,
    section_grades: [section(
      "Efficacy",
      dimensions(grade("critical"), grade("critical"), grade("not_applicable")),
      [variable("Duration of protection", "missing", dimensions(
        grade("critical", [], ["Required variable is missing."]),
        grade("critical", [], ["Required rubric structure is absent."]),
        grade("not_applicable"),
      ))],
      ["b-1", "b-2"],
    )],
  }));

  assert.equal(annotations.length, 2, "completeness and adherence; rigor is N/A");
  for (const annotation of annotations) {
    assert.deepEqual(annotation.blockIds, [], "an absence cites nothing");
    assert.equal(annotation.displayAnchorBlockId, "b-2", "last mapped block");
    assert.match(annotation.statusLabel ?? "", /^Not present/);
  }
});

test("a placeholder is reported as a placeholder, not as a gap", () => {
  // `placeholder` and `missing` were indistinguishable before the canonical layer
  // published `content_status`; this is the distinction that could not be made.
  const annotations = buildInspectorDocumentAnnotations(result({
    blocks: BLOCKS,
    section_grades: [section("Efficacy", NA, [
      variable("Dose volume", "placeholder", dimensions(
        grade("critical", ["b-2"], ["Only a placeholder token is present."]),
        grade("not_applicable"),
        grade("not_applicable"),
      )),
    ], ["b-1", "b-2"])],
  }));

  assert.equal(annotations.length, 1);
  assert.deepEqual(annotations[0].blockIds, ["b-2"], "a placeholder is present text");
  assert.equal(annotations[0].displayAnchorBlockId, undefined);
  assert.match(annotations[0].statusLabel ?? "", /^Placeholder/);
});

test("an unwritten section maps no blocks, so its gap has no anchor", () => {
  const annotations = buildInspectorDocumentAnnotations(result({
    blocks: BLOCKS,
    section_grades: [section(
      "Manufacturing",
      dimensions(grade("critical"), grade("not_applicable"), grade("not_applicable")),
      [variable("Fill-finish capacity", "missing", dimensions(
        grade("critical", [], ["Required variable is missing."]),
        grade("not_applicable"),
        grade("not_applicable"),
      ))],
      [],
      false,
    )],
  }));

  assert.equal(annotations.length, 1);
  assert.equal(annotations[0].displayAnchorBlockId, undefined);
  const trace = buildDocumentTrace(BLOCKS, annotations);
  assert.deepEqual(trace.unplacedAnnotationIds, [annotations[0].id]);
});

test("a present prose section is scoped to its blocks, not reported absent", () => {
  // A section-level grade covers every block the section maps. Treating that as
  // absence made a section that exists and scores well read as missing.
  const annotations = buildInspectorDocumentAnnotations(result({
    blocks: BLOCKS,
    section_grades: [section(
      "Safety",
      dimensions(grade("meets"), grade("not_applicable"), grade("not_applicable")),
      [],
      ["b-3"],
    )],
  }));

  assert.equal(annotations.length, 1);
  assert.equal(annotations[0].title, "Safety");
  assert.deepEqual(annotations[0].blockIds, ["b-3"], "the section's scope is lineage");
  assert.equal(annotations[0].displayAnchorBlockId, undefined, "a present section is not anchored");
});

test("an absent prose section maps no blocks and is anchored", () => {
  const annotations = buildInspectorDocumentAnnotations(result({
    blocks: BLOCKS,
    section_grades: [section(
      "Manufacturing",
      dimensions(grade("critical", [], ["Section is absent."]), grade("not_applicable"), grade("not_applicable")),
      [],
      [],
      false,
    )],
  }));

  assert.equal(annotations.length, 1);
  assert.deepEqual(annotations[0].blockIds, []);
  const trace = buildDocumentTrace(BLOCKS, annotations);
  assert.deepEqual(trace.unplacedAnnotationIds, [annotations[0].id]);
});

test("a clean grade does not borrow its recommendation as the finding", () => {
  // The grader answers "nothing to recommend" in prose. Using that as the
  // summary made an A-graded section read "None."
  const annotations = buildInspectorDocumentAnnotations(result({
    blocks: BLOCKS,
    section_grades: [section(
      "Safety",
      dimensions(grade("meets", [], [], "None."), grade("not_applicable"), grade("not_applicable")),
      [],
      ["b-3"],
    )],
  }));

  assert.equal(annotations[0].summary, "No issue recorded.");
});

test("cross-section findings are always danger and keep their lineage", () => {
  const annotations = buildInspectorDocumentAnnotations(result({
    blocks: BLOCKS,
    cross_section_findings: [{
      description: "Efficacy targets 60% while Safety assumes 90%.",
      sections: ["Efficacy", "Safety"],
      recommendation: "Reconcile the two figures.",
      block_ids: ["b-2", "b-3"],
    }],
  }));

  assert.equal(annotations.length, 1);
  assert.equal(annotations[0].kind, "consistency");
  assert.equal(annotations[0].title, "Efficacy ↔ Safety");
  assert.deepEqual(annotations[0].blockIds, ["b-2", "b-3"]);
  assert.equal(annotations[0].emphasis?.tone, "danger");
});

test("the input result is not mutated and projection is deterministic", () => {
  const input = result({
    blocks: BLOCKS,
    section_grades: [section(
      "Efficacy",
      dimensions(grade("for_consideration"), grade("for_consideration"), grade("for_consideration")),
      [
        variable("Seroconversion rate", "substantive", dimensions(
          grade("meets", ["b-2"]),
          grade("for_consideration", ["b-2"]),
          grade("critical", ["b-2"]),
        )),
        variable("Duration of protection", "missing", dimensions(
          grade("critical"),
          grade("critical"),
          grade("not_applicable"),
        )),
      ],
      ["b-1", "b-2"],
    )],
    cross_section_findings: [{
      description: "d",
      sections: ["Efficacy"],
      recommendation: "r",
      block_ids: ["b-2"],
    }],
  });
  const snapshot = JSON.stringify(input);
  const first = buildInspectorDocumentAnnotations(input);
  const second = buildInspectorDocumentAnnotations(input);

  assert.equal(JSON.stringify(input), snapshot, "input must not be mutated");
  assert.deepEqual(first, second, "projection must be deterministic");
});
