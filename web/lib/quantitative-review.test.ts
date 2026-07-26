import assert from "node:assert/strict";
import test from "node:test";
import type { Conformity, Measurement } from "./api.ts";
import {
  reviewQuantitativeCandidate,
  reviewQuantitativeCandidateGroup,
} from "./quantitative-review.ts";

function candidate(id: string, value: number): Measurement {
  return {
    candidate_id: id,
    expression: {
      kind: "point_estimate",
      value,
      lower: null,
      upper: null,
      comparator: "",
      unit: "%",
    },
    url: `https://example.test/${id}`,
    insight_id: id,
    source_quote: `The result was ${value}%.`,
    source_record_id: id,
    source_identity_status: "canonical",
    evidence_unit_id: `${id}/unit:record`,
    evidence_unit: {
      status: "record_level",
      group: { state: "not_specified", value: "", other: "" },
      cohort: { state: "not_specified", value: "", other: "" },
      reason: "One aggregate source group.",
    },
    semantic_assessment: {} as Measurement["semantic_assessment"],
    semantic_status: "comparable",
    semantic_reason: "Compatible result.",
    evidence_mode: "prose",
    admission_status: "needs_review",
    admission_reason: "Review required.",
    inclusion_reason: "",
    exclusion_reasons: ["Review required."],
    age_months: null,
  };
}

function score(): Conformity {
  return {
    attribute_ref: "efficacy",
    target_id: "target",
    target_role: "threshold",
    target_value: 80,
    comparator: ">=",
    unit: "%",
    target_label: "efficacy >=80%",
    target_quote: "Target efficacy >=80%.",
    target_meeting_count: 0,
    target_meeting_rate: 0,
    verdict: "No admitted comparators",
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
    doc_block_ids: [],
    measurements: [],
    excluded_measurements: [candidate("low", 70), candidate("high", 90)],
    source_dispositions: [],
  };
}

test("only an explicit approval enters deterministic statistics", () => {
  const reviewed = reviewQuantitativeCandidate(score(), "high", "approve");
  assert.equal(reviewed.benchmark_count, 1);
  assert.equal(reviewed.benchmark_median, 90);
  assert.equal(reviewed.target_meeting_count, 1);
  assert.equal(reviewed.measurements[0].admission_status, "approved");
  assert.equal(reviewed.excluded_measurements[0].candidate_id, "low");
});

test("a rejection remains traceable and never changes statistics", () => {
  const reviewed = reviewQuantitativeCandidate(score(), "high", "reject");
  assert.equal(reviewed.benchmark_count, 0);
  assert.equal(reviewed.measurements.length, 0);
  assert.equal(
    reviewed.excluded_measurements.find((item) => item.candidate_id === "high")?.admission_status,
    "rejected",
  );
});

test("distinct evidence units from one source both enter the cohort", () => {
  const sharedSource = score();
  sharedSource.excluded_measurements = sharedSource.excluded_measurements.map((item, index) => ({
    ...item,
    source_record_id: "doi:shared",
    evidence_unit_id: `doi:shared/unit:arm-${index + 1}`,
  }));
  const first = reviewQuantitativeCandidate(sharedSource, "low", "approve");
  const second = reviewQuantitativeCandidate(first, "high", "approve");

  assert.equal(second.benchmark_count, 2);
  assert.deepEqual(second.measurements.map((item) => item.expression.value), [70, 90]);
});

test("one grouped choice resolves alternative estimates from one evidence unit", () => {
  const alternatives = score();
  alternatives.excluded_measurements = alternatives.excluded_measurements.map((item) => ({
    ...item,
    source_record_id: "doi:shared",
    evidence_unit_id: "doi:shared/unit:adult-arm",
  }));

  const reviewed = reviewQuantitativeCandidateGroup(
    alternatives,
    ["low", "high"],
    "high",
  );
  assert.equal(reviewed.benchmark_count, 1);
  assert.equal(reviewed.measurements[0].candidate_id, "high");
  assert.equal(
    reviewed.excluded_measurements.find((item) => item.candidate_id === "low")?.admission_status,
    "rejected",
  );
});

test("none applies rejects every alternative without changing statistics", () => {
  const alternatives = score();
  alternatives.excluded_measurements = alternatives.excluded_measurements.map((item) => ({
    ...item,
    evidence_unit_id: "doi:shared/unit:adult-arm",
  }));
  const reviewed = reviewQuantitativeCandidateGroup(
    alternatives,
    ["low", "high"],
    null,
  );
  assert.equal(reviewed.benchmark_count, 0);
  assert.ok(reviewed.excluded_measurements.every(
    (item) => item.admission_status === "rejected",
  ));
});
