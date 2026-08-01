/**
 * The Inspector trace adapter is a projection, so these tests assert it reports
 * exactly what the result already says and invents nothing.
 */

import assert from "node:assert/strict";
import test from "node:test";

import type { ContentBlock, Grade, InspectionResult } from "./api.ts";
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

function grade(value: Grade, issues: string[] = [], recommendation = "") {
  return { grade: value, issues, recommendation };
}

function dimensions(completeness: Grade, adherence: Grade, rigor: Grade) {
  return {
    completeness: grade(completeness),
    adherence: grade(adherence),
    rigor: grade(rigor),
  };
}

function result(overrides: Partial<InspectionResult> = {}): InspectionResult {
  return {
    doc_id: "plan",
    dimensions: dimensions("B", "B", "B"),
    top_issues: [],
    section_grades: [],
    cross_section_findings: [],
    consistency_status: "complete",
    grading_status: "complete",
    org: "bmgf",
    source_type: "itpp",
    intervention_class: "vaccine",
    indication: "malaria",
    blocks: [],
    ...overrides,
  };
}

const EFFICACY_BLOCKS = [
  block("b-1", 1, "Efficacy", "Efficacy"),
  block("b-2", 2, "Minimum: 60% seroconversion", "Efficacy"),
  block("b-3", 3, "Safety", "Safety"),
];

test("projects one annotation per graded variable dimension", () => {
  const annotations = buildInspectorDocumentAnnotations(result({
    blocks: EFFICACY_BLOCKS,
    section_grades: [{
      section_name: "Efficacy",
      is_present: true,
      dimensions: dimensions("B", "B", "B"),
      missing_variables: [],
      variable_grades: [{
        variable_name: "Seroconversion rate",
        dimensions: dimensions("A", "B", "D"),
        block_ids: ["b-2"],
      }],
    }],
  }));

  assert.deepEqual(
    annotations.map((item) => [item.kind, item.statusLabel]),
    [["completeness", "A"], ["adherence", "B"], ["rigor", "D"]],
  );
  assert.deepEqual(annotations.map((item) => item.blockIds), [["b-2"], ["b-2"], ["b-2"]]);
});

test("maps every grade to its tone and carries the grade as text", () => {
  const cases: Array<[Grade, string]> = [
    ["A", "neutral"],
    ["B", "neutral"],
    ["C", "caution"],
    ["D", "danger"],
    ["F", "danger"],
  ];
  for (const [value, tone] of cases) {
    const annotations = buildInspectorDocumentAnnotations(result({
      blocks: EFFICACY_BLOCKS,
      section_grades: [{
        section_name: "Efficacy",
        is_present: true,
        dimensions: dimensions("N/A", "N/A", "N/A"),
        missing_variables: [],
        variable_grades: [{
          variable_name: "V",
          dimensions: dimensions(value, "N/A", "N/A"),
          block_ids: ["b-2"],
        }],
      }],
    }));
    assert.equal(annotations.length, 1, `grade ${value} should emit once`);
    assert.deepEqual(annotations[0].emphasis, { tone, badge: value });
  }
});

test("skips N/A dimensions because the rubric does not apply", () => {
  const annotations = buildInspectorDocumentAnnotations(result({
    blocks: EFFICACY_BLOCKS,
    section_grades: [{
      section_name: "Efficacy",
      is_present: true,
      dimensions: dimensions("N/A", "N/A", "N/A"),
      missing_variables: [],
      variable_grades: [{
        variable_name: "V",
        dimensions: dimensions("N/A", "N/A", "N/A"),
        block_ids: ["b-2"],
      }],
    }],
  }));
  assert.deepEqual(annotations, []);
});

test("a missing variable is not double-counted and anchors to its section", () => {
  // The grader gives a missing variable a VariableGrade *and* lists it in
  // missing_variables. Reading both sources would emit each gap twice.
  const annotations = buildInspectorDocumentAnnotations(result({
    blocks: EFFICACY_BLOCKS,
    section_grades: [{
      section_name: "Efficacy",
      is_present: true,
      dimensions: dimensions("F", "F", "N/A"),
      missing_variables: ["Dosing schedule"],
      variable_grades: [{
        variable_name: "Dosing schedule",
        dimensions: dimensions("F", "F", "N/A"),
        block_ids: [],
      }],
    }],
  }));

  assert.equal(annotations.length, 2, "completeness and adherence, rigor is N/A");
  for (const annotation of annotations) {
    assert.deepEqual(annotation.blockIds, [], "an absence cites nothing");
    assert.equal(
      annotation.displayAnchorBlockId,
      "b-2",
      "anchors to the last block of the Efficacy section",
    );
    assert.match(annotation.statusLabel ?? "", /^Missing/);
  }
});

test("an absence in an unwritten section gets no anchor", () => {
  const annotations = buildInspectorDocumentAnnotations(result({
    blocks: EFFICACY_BLOCKS,
    section_grades: [{
      section_name: "Manufacturing",
      is_present: false,
      dimensions: dimensions("F", "N/A", "N/A"),
      missing_variables: ["Fill-finish capacity"],
      variable_grades: [{
        variable_name: "Fill-finish capacity",
        dimensions: dimensions("F", "N/A", "N/A"),
        block_ids: [],
      }],
    }],
  }));

  assert.equal(annotations.length, 1);
  assert.equal(annotations[0].displayAnchorBlockId, undefined);
  // The viewer must still be able to reach it.
  const trace = buildDocumentTrace(EFFICACY_BLOCKS, annotations);
  assert.deepEqual(trace.unplacedAnnotationIds, [annotations[0].id]);
});

test("prose sections are anchored because they carry no block IDs", () => {
  const annotations = buildInspectorDocumentAnnotations(result({
    blocks: EFFICACY_BLOCKS,
    section_grades: [{
      section_name: "Safety",
      is_present: true,
      dimensions: dimensions("C", "N/A", "N/A"),
      missing_variables: [],
      variable_grades: [],
    }],
  }));

  assert.equal(annotations.length, 1);
  assert.equal(annotations[0].title, "Safety");
  assert.deepEqual(annotations[0].blockIds, []);
  assert.equal(annotations[0].displayAnchorBlockId, "b-3");
});

test("cross-section findings are always danger and keep their lineage", () => {
  const annotations = buildInspectorDocumentAnnotations(result({
    blocks: EFFICACY_BLOCKS,
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

test("anchoring uses the last block of a section, not the first", () => {
  const annotations = buildInspectorDocumentAnnotations(result({
    blocks: [
      block("b-1", 1, "Efficacy", "Efficacy"),
      block("b-2", 2, "First target", "Efficacy"),
      block("b-9", 9, "Last target", "Efficacy"),
    ],
    section_grades: [{
      section_name: "Efficacy",
      is_present: true,
      dimensions: dimensions("F", "N/A", "N/A"),
      missing_variables: ["Gap"],
      variable_grades: [{
        variable_name: "Gap",
        dimensions: dimensions("F", "N/A", "N/A"),
        block_ids: [],
      }],
    }],
  }));
  assert.equal(annotations[0].displayAnchorBlockId, "b-9");
});

test("the input result is not mutated", () => {
  const input = result({
    blocks: EFFICACY_BLOCKS,
    section_grades: [{
      section_name: "Efficacy",
      is_present: true,
      dimensions: dimensions("B", "B", "B"),
      missing_variables: ["Gap"],
      variable_grades: [{
        variable_name: "Seroconversion rate",
        dimensions: dimensions("A", "B", "D"),
        block_ids: ["b-2"],
      }],
    }],
    cross_section_findings: [{
      description: "d",
      sections: ["Efficacy"],
      recommendation: "r",
      block_ids: ["b-2"],
    }],
  });
  const snapshot = JSON.stringify(input);
  buildInspectorDocumentAnnotations(input);
  assert.equal(JSON.stringify(input), snapshot);
});

test("projection is deterministic", () => {
  const input = result({
    blocks: EFFICACY_BLOCKS,
    section_grades: [{
      section_name: "Efficacy",
      is_present: true,
      dimensions: dimensions("B", "B", "B"),
      missing_variables: [],
      variable_grades: [{
        variable_name: "V",
        dimensions: dimensions("A", "C", "F"),
        block_ids: ["b-2"],
      }],
    }],
  });
  assert.deepEqual(
    buildInspectorDocumentAnnotations(input),
    buildInspectorDocumentAnnotations(input),
  );
});
