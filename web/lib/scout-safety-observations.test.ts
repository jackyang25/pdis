import assert from "node:assert/strict";
import test from "node:test";

import type { SafetyObservation } from "./api.ts";
import {
  groupSafetyObservations,
  safetyObservationCountLabel,
  safetySourceSystemLabel,
} from "./scout-safety-observations.ts";

function observation(
  overrides: Partial<SafetyObservation> & Pick<SafetyObservation, "projection_id">,
): SafetyObservation {
  const { projection_id, ...rest } = overrides;
  return {
    projection_id,
    product_name: "Product A",
    record_type: "label_warning",
    source_system: "fda_label",
    label: "Boxed warning",
    detail: "Official prescribing information.",
    report_count: null,
    qualification: "FDA labeling record.",
    source_role: "unknown",
    target_relationship: "direct",
    target_relationship_reason: "Matches the uploaded product.",
    attribute_refs: [],
    supporting_findings: [],
    ...rest,
  };
}

const observations = [
  observation({ projection_id: "label" }),
  observation({
    projection_id: "faers",
    record_type: "reported_event",
    source_system: "faers",
    label: "Drug ineffective",
    detail: "Spontaneous report summary.",
    report_count: 12,
    target_relationship: "analogous",
  }),
  observation({
    projection_id: "recall",
    record_type: "recall",
    source_system: "fda_recall",
    label: "Class II recall",
  }),
  observation({
    projection_id: "maude",
    record_type: "device_event",
    source_system: "maude",
    label: "Device malfunction",
  }),
];

test("groups observations into stable, non-empty safety sections", () => {
  const sections = groupSafetyObservations(observations);

  assert.deepEqual(
    sections.map((section) => section.key),
    ["official", "surveillance"],
  );
  assert.deepEqual(
    sections[0].observations.map((item) => item.projection_id),
    ["label", "recall"],
  );
  assert.deepEqual(
    sections[1].observations.map((item) => item.projection_id),
    ["faers", "maude"],
  );
});

test("omits an empty safety section", () => {
  const sections = groupSafetyObservations([observations[1]]);

  assert.equal(sections.length, 1);
  assert.equal(sections[0].key, "surveillance");
});

test("filters relationships without changing or dropping matching records", () => {
  const sections = groupSafetyObservations(observations, {
    relationship: "analogous",
  });

  assert.deepEqual(
    sections.flatMap((section) => section.observations),
    [observations[1]],
  );
  assert.equal(observations.length, 4);
});

test("searches product, label, detail, qualification, and source labels", () => {
  assert.equal(groupSafetyObservations(observations, { query: "spontaneous" })[0].observations[0].projection_id, "faers");
  assert.equal(groupSafetyObservations(observations, { query: "recall" })[0].observations[0].projection_id, "recall");
  assert.equal(groupSafetyObservations(observations, { query: "maude" })[0].observations[0].projection_id, "maude");
});

test("uses plain source-system labels", () => {
  assert.equal(safetySourceSystemLabel("fda_label"), "FDA labeling");
  assert.equal(safetySourceSystemLabel("faers"), "FDA adverse event reporting system (FAERS)");
  assert.equal(safetySourceSystemLabel("maude"), "FDA device event reporting (MAUDE)");
  assert.equal(safetySourceSystemLabel("fda_recall"), "FDA recalls");
});

test("shows source-supplied report counts for FAERS only", () => {
  assert.equal(safetyObservationCountLabel(observations[1]), "12 reports");
  assert.equal(safetyObservationCountLabel(observations[0]), null);
  assert.equal(safetyObservationCountLabel(observations[2]), null);
  assert.equal(safetyObservationCountLabel(observations[3]), null);
});
