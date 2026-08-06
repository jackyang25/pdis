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
          status_counts: { met: 0, could_be_stronger: 0, not_met: 1, not_applicable: 0 },
          units: [
            {
              variable_name: "Efficacy",
              optional: false,
              status: "not_met",
              findings: [
                {
                  id: "f1",
                  reason: "missing",
                  statement: "Not stated.",
                  recommendation: "State it.",
                  section_name: "Profile",
                  variable_name: "Efficacy",
                  cited_block_ids: [],
                  rank: 0,
                  level: "not_met",
                },
              ],
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

  assert.deepEqual(Object.keys(inspectorItem).sort(), Object.keys(scoutItem).sort());
});

test("Inspector reuses the rank the result already assigned", () => {
  // Re-deriving the order in the view would be a second opinion that could disagree
  // with the sections below it.
  const finding = (id: string, rank: number) => ({
    id,
    reason: "unclear" as const,
    statement: id,
    recommendation: "",
    section_name: "Profile",
    variable_name: id,
    cited_block_ids: ["b1"],
    rank,
    level: "could_be_stronger" as const,
  });
  const unit = (name: string, rank: number) => ({
    variable_name: name,
    optional: false,
    status: "could_be_stronger" as const,
    findings: [finding(name, rank)],
  });

  const items = selectInspectorPriorities(
    inspection({
      sections: [
        {
          section_name: "Profile",
          mapped_block_ids: ["b1"],
          is_present: true,
          status_counts: { met: 0, could_be_stronger: 2, not_met: 0, not_applicable: 0 },
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
