/**
 * Both tools open with the same panel, and neither owns it.
 *
 * The container renders whatever a selector returns and has no opinion about
 * rubrics, targets, or evidence. That is what makes the priorities improvable: when
 * a rubric arrives, one selector changes and nothing else does. These tests pin that
 * separation, because it is the kind that erodes quietly.
 */

import assert from "node:assert/strict";
import test from "node:test";

import type { InspectionResult, ScoutResponse } from "./api.ts";
import {
  INSPECTOR_EMPTY_MESSAGE,
  INSPECTOR_ORDER_NOTE,
  selectInspectorPriorities,
} from "./inspector-priorities.ts";
import {
  SCOUT_EMPTY_MESSAGE,
  SCOUT_ORDER_NOTE,
  SCOUT_PRIORITY_LIMIT,
  selectScoutPriorities,
} from "./scout-priorities.ts";

function inspection(overrides: Partial<InspectionResult> = {}): InspectionResult {
  return {
    doc_id: "plan",
    sections: [],
    document_findings: [],
    consistency_status: "complete",
    assessment_status: "complete",
    org: null,
    source_type: null,
    intervention_class: null,
    indication: null,
    blocks: [],
    ...overrides,
  };
}

function scout(overrides: Partial<ScoutResponse> = {}): ScoutResponse {
  return { matches: [], assessments: [], conformity: [], ...overrides } as ScoutResponse;
}

test("both selectors return the same item shape", () => {
  // The shared contract. A field either makes sense for a rubric gap AND a
  // contradicted target, or it does not belong in the panel every tool shares.
  const inspectorItem = selectInspectorPriorities(
    inspection({
      sections: [
        {
          section_name: "Profile",
          mapped_block_ids: ["b1"],
          is_present: true,
          verdict_counts: { not_present: 1 } as never,
          units: [
            {
              id: "Profile|Efficacy",
              verdict: "not_present",
              statement: "Not stated.",
              section_name: "Profile",
              variable_name: "Efficacy",
              optional: false,
              cited_block_ids: [],
              rank: 0,
            },
          ],
        },
      ],
    }),
  )[0];

  const scoutItem = selectScoutPriorities(
    scout({
      assessments: [
        {
          attribute_ref: "vaccine.efficacy",
          strength: "unsupported",
          reason: "Nothing found.",
          doc_target: "at least 80%",
          doc_block_ids: ["b2"],
          supporting_insight_ids: [],
          supporting_findings: [],
        },
      ],
    }),
  )[0];

  // Every key each selector emits has to be one the shared item declares. Equality of
  // the two key sets was the old check, and it stopped being the right one when
  // Inspector lost its `recommendation`: that field restated the statement beside it,
  // so removing it was the point. Scout's is a different thing under the same name -
  // the evidence's own reason - and it stays.
  const DECLARED = [
    "id",
    "label",
    "qualifier",
    "statement",
    "recommendation",
    "blockIds",
  ];
  for (const [tool, item] of [
    ["inspector", inspectorItem],
    ["scout", scoutItem],
  ] as const) {
    for (const key of Object.keys(item)) {
      assert.ok(DECLARED.includes(key), `${tool} emits ${key}, which no other tool has`);
    }
  }
  // The two that make no sense to omit: without them the panel has no row and no link.
  for (const required of ["id", "label", "statement"]) {
    assert.ok(required in inspectorItem, `inspector omits ${required}`);
    assert.ok(required in scoutItem, `scout omits ${required}`);
  }
});

test("Inspector reuses the rank the result already assigned", () => {
  // Re-deriving the order in the view would be a second opinion that could disagree
  // with the sections below it.
  const unit = (name: string, rank: number) => ({
    id: `Profile|${name}`,
    verdict: "vague" as const,
    statement: name,
    section_name: "Profile",
    variable_name: name,
    optional: false,
    cited_block_ids: ["b1"],
    rank,
  });

  const items = selectInspectorPriorities(
    inspection({
      sections: [
        {
          section_name: "Profile",
          mapped_block_ids: ["b1"],
          is_present: true,
          verdict_counts: { vague: 2 } as never,
          units: [unit("later", 5), unit("sooner", 1)],
        },
      ],
    }),
  );

  assert.deepEqual(items.map((i) => i.label), ["sooner", "later"]);
});

test("Scout raises a contradicted target above an unsupported one", () => {
  const items = selectScoutPriorities(
    scout({
      assessments: [
        {
          attribute_ref: "vaccine.safety",
          strength: "unsupported",
          reason: "Nothing found.",
          doc_target: "no SAEs",
          doc_block_ids: [],
          supporting_insight_ids: [],
          supporting_findings: [],
        },
      ],
      matches: [
        {
          relation: "contradicts",
          reason: "Trial reports 40%.",
          doc_block_ids: ["b1"],
          insight: {
            statement: "Observed efficacy was 40%.",
            query: "q",
            attribute_ref: "vaccine.efficacy",
            supporting_findings: [],
            org: null,
            source_type: null,
            intervention_class: null,
            indication: null,
          },
        },
      ],
    }),
  );

  assert.deepEqual(items.map((i) => i.label), ["Efficacy", "Safety"]);
});

test("Scout raises each target once, keeping the stronger claim", () => {
  const items = selectScoutPriorities(
    scout({
      assessments: [
        {
          attribute_ref: "vaccine.efficacy",
          strength: "unsupported",
          reason: "Nothing found.",
          doc_target: "at least 80%",
          doc_block_ids: [],
          supporting_insight_ids: [],
          supporting_findings: [],
        },
      ],
      matches: [
        {
          relation: "contradicts",
          reason: "Trial reports 40%.",
          doc_block_ids: [],
          insight: {
            statement: "Observed efficacy was 40%.",
            query: "q",
            attribute_ref: "vaccine.efficacy",
            supporting_findings: [],
            org: null,
            source_type: null,
            intervention_class: null,
            indication: null,
          },
        },
      ],
    }),
  );

  assert.equal(items.length, 1);
  assert.equal(items[0].qualifier, "Evidence contradicts this target");
});

test("Scout does not raise a target it could not calibrate", () => {
  // "insufficient" means no comparator cohort existed, which is not the same as
  // falling short of the target.
  // Only the fields the selector reads; the rest of Conformity is irrelevant here
  // and spelling it out would tie this test to an unrelated shape.
  const score = (calibration: string, rate: number, count: number) =>
    ({
      attribute_refs: ["vaccine.efficacy"],
      target_id: `t-${calibration}-${rate}`,
      target_label: "at least 80%",
      target_meeting_rate: rate,
      benchmark_count: count,
      calibration_status: calibration,
      verdict: "v",
      doc_block_ids: [],
    }) as unknown as ScoutResponse["conformity"][number];

  const uncalibrated = selectScoutPriorities(
    scout({ conformity: [score("insufficient", 0, 0)] }),
  );
  const unmet = selectScoutPriorities(
    scout({ conformity: [score("sufficient", 0, 12)] }),
  );

  assert.deepEqual(uncalibrated, []);
  assert.equal(unmet.length, 1);
  assert.match(unmet[0].qualifier ?? "", /12 measured/);
});

test("Scout's list is bounded", () => {
  const many = Array.from({ length: 30 }, (_, i) => ({
    attribute_ref: `vaccine.field_${i}`,
    strength: "unsupported" as const,
    reason: "Nothing found.",
    doc_target: "t",
    doc_block_ids: [],
    supporting_insight_ids: [],
    supporting_findings: [],
  }));

  assert.equal(selectScoutPriorities(scout({ assessments: many })).length, SCOUT_PRIORITY_LIMIT);
});

test("an empty result yields no items, not a placeholder row", () => {
  assert.deepEqual(selectInspectorPriorities(inspection()), []);
  assert.deepEqual(selectScoutPriorities(scout()), []);
});

test("each tool states how its own order was decided", () => {
  // The sparkle marks the wording as the model's; it does not cover the ordering,
  // so each note has to say what produced it.
  assert.match(INSPECTOR_ORDER_NOTE, /order is not/i);
  assert.match(SCOUT_ORDER_NOTE, /placeholder/i);
  assert.ok(INSPECTOR_EMPTY_MESSAGE && SCOUT_EMPTY_MESSAGE);
});
