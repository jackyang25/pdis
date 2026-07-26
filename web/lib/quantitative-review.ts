import type { Conformity, Measurement } from "./api";

export type QuantitativeReviewDecision = "approve" | "reject";

export type EvidenceReviewRecommendationSummary = {
  admit: number;
  reject: number;
  flag: number;
  total: number;
};

/** Count one recommendation per target/evidence-unit review decision. */
export function evidenceReviewRecommendationSummary(
  scores: Conformity[],
): EvidenceReviewRecommendationSummary {
  const summary = { admit: 0, reject: 0, flag: 0, total: 0 };
  for (const score of scores) {
    for (const candidates of pendingEvidenceUnits(score)) {
      const recommendation = groupRecommendation(candidates);
      summary[recommendation] += 1;
      summary.total += 1;
    }
  }
  return summary;
}

/** Apply every complete AI recommendation; flagged groups remain pending. */
export function applyEvidenceReviewRecommendations(
  scores: Conformity[],
): Conformity[] {
  return scores.map((original) => {
    let score = original;
    for (const candidates of pendingEvidenceUnits(original)) {
      const recommendation = groupRecommendation(candidates);
      if (recommendation === "flag") continue;
      const selected = recommendation === "admit"
        ? candidates.find((candidate) => candidate.ai_recommendation === "admit")
        : undefined;
      score = reviewQuantitativeCandidateGroup(
        score,
        candidates.map((candidate) => candidate.candidate_id),
        selected?.candidate_id ?? null,
      );
    }
    return score;
  });
}

/**
 * Apply one explicit human admission decision and deterministically rebuild the
 * descriptive cohort. No retrieval or AI call occurs; the returned object is
 * portable and becomes the value exported in the result envelope.
 */
export function reviewQuantitativeCandidate(
  score: Conformity,
  candidateId: string,
  decision: QuantitativeReviewDecision,
): Conformity {
  return reviewQuantitativeCandidateGroup(
    score,
    [candidateId],
    decision === "approve" ? candidateId : null,
  );
}

/** Resolve every alternative estimate for one target/evidence-unit decision. */
export function reviewQuantitativeCandidateGroup(
  score: Conformity,
  candidateIds: string[],
  selectedCandidateId: string | null,
): Conformity {
  const all = [...score.measurements, ...score.excluded_measurements];
  const requested = new Set(candidateIds);
  const candidates = all.filter((item) => requested.has(item.candidate_id));
  if (
    candidates.length !== requested.size
    || candidates.some((item) => item.admission_status !== "needs_review")
    || (selectedCandidateId != null && !requested.has(selectedCandidateId))
  ) return score;

  const unitIds = new Set(candidates.map(evidenceUnitId));
  if (unitIds.size !== 1) return score;

  const byId = new Map(all.map((item) => [item.candidate_id, item]));
  for (const candidate of candidates) {
    const approved = candidate.candidate_id === selectedCandidateId;
    byId.set(candidate.candidate_id, {
      ...candidate,
      admission_status: approved ? "approved" : "rejected",
      admission_reason: approved
        ? "Explicitly selected by a user for this independent evidence unit."
        : selectedCandidateId == null
          ? "Explicitly rejected by a user for this independent evidence unit."
          : "Not selected among alternative estimates from this independent evidence unit.",
      inclusion_reason: approved
        ? "Manually selected; typed calculation inputs and evidence-unit deduplication were retained."
        : "",
      exclusion_reasons: approved
        ? []
        : [selectedCandidateId == null
          ? "Explicitly rejected during quantitative evidence review."
          : "Another estimate was selected for this independent evidence unit."],
    });
  }
  const included = Array.from(byId.values()).filter((item) =>
    item.admission_status === "approved" || item.admission_status === "auto_admitted"
  );
  const excluded = Array.from(byId.values()).filter((item) =>
    item.admission_status !== "approved" && item.admission_status !== "auto_admitted"
  );
  return calculateCohort(score, included, excluded);
}

function calculateCohort(
  score: Conformity,
  included: Measurement[],
  excluded: Measurement[],
): Conformity {
  const deduplicated: Measurement[] = [];
  const retainedExcluded = [...excluded];
  const byUnit = new Map<string, Measurement[]>();
  for (const measurement of included) {
    const unitId = evidenceUnitId(measurement);
    byUnit.set(
      unitId,
      [...(byUnit.get(unitId) ?? []), measurement],
    );
  }
  for (const [unitId, measurements] of byUnit) {
    const valid = measurements.filter((item) =>
      item.expression.value != null && Number.isFinite(item.expression.value)
    );
    const values = new Set(valid.map((item) => item.expression.value));
    if (values.size > 1) {
      retainedExcluded.push(...valid.map((item) => ({
        ...item,
        admission_status: "needs_review" as const,
        admission_reason: `Multiple candidate values remain for evidence unit ${unitId}; select one estimate.`,
        inclusion_reason: "",
        exclusion_reasons: ["Alternative scalar values from one evidence unit require one review choice."],
      })));
      continue;
    }
    const [selected, ...duplicates] = valid;
    if (selected) deduplicated.push(selected);
    retainedExcluded.push(...duplicates.map((item) => ({
      ...item,
      admission_status: "not_eligible" as const,
      admission_reason: `Duplicate evidence unit and value: ${unitId}.`,
      inclusion_reason: "",
      exclusion_reasons: [`Duplicate evidence unit and value: ${unitId}.`],
    })));
  }
  const values = deduplicated
    .map((item) => item.expression.value as number)
    .sort((left, right) => left - right);
  const count = values.length;
  const meetingCount = values.filter((value) => meetsTarget(
    value,
    score.target_value,
    score.comparator,
  )).length;
  const rawPercentile = count ? empiricalPercentile(values, score.target_value) : null;
  const ambitionPercentile = rawPercentile == null || score.comparator === "="
    ? null
    : score.comparator === "<" || score.comparator === "<="
      ? 1 - rawPercentile
      : rawPercentile;
  return {
    ...score,
    measurements: deduplicated,
    excluded_measurements: retainedExcluded,
    target_meeting_count: meetingCount,
    target_meeting_rate: count ? round(meetingCount / count) : 0,
    verdict: count
      ? `${meetingCount} of ${count} admitted comparators meet the document target`
      : "No admitted comparators",
    benchmark_count: count,
    benchmark_minimum: count ? values[0] : null,
    benchmark_maximum: count ? values[count - 1] : null,
    benchmark_mean: count ? round(values.reduce((sum, value) => sum + value, 0) / count) : null,
    benchmark_median: quantile(values, 0.5),
    benchmark_lower_quartile: quantile(values, 0.25),
    benchmark_upper_quartile: quantile(values, 0.75),
    benchmark_standard_deviation: sampleStandardDeviation(values),
    target_percentile: rawPercentile == null ? null : round(rawPercentile),
    ambition_percentile: ambitionPercentile == null ? null : round(ambitionPercentile),
    calibration_status: count >= 5 ? "sufficient" : count >= 2 ? "limited" : "insufficient",
  };
}

function evidenceUnitId(measurement: Measurement): string {
  return measurement.evidence_unit_id || measurement.source_record_id;
}

function pendingEvidenceUnits(score: Conformity): Measurement[][] {
  const byUnit = new Map<string, Measurement[]>();
  for (const measurement of [...score.measurements, ...score.excluded_measurements]) {
    if (
      measurement.evidence_mode !== "prose"
      || measurement.admission_status !== "needs_review"
    ) continue;
    const unitId = evidenceUnitId(measurement);
    byUnit.set(unitId, [...(byUnit.get(unitId) ?? []), measurement]);
  }
  return Array.from(byUnit.values());
}

function groupRecommendation(
  candidates: Measurement[],
): "admit" | "reject" | "flag" {
  const admitted = candidates.filter(
    (candidate) => candidate.ai_recommendation === "admit",
  );
  if (
    admitted.length === 1
    && candidates.every((candidate) =>
      candidate.ai_recommendation === "admit"
      || candidate.ai_recommendation === "reject"
    )
  ) return "admit";
  if (
    candidates.length > 0
    && candidates.every((candidate) => candidate.ai_recommendation === "reject")
  ) return "reject";
  return "flag";
}

function meetsTarget(value: number, target: number, comparator: Conformity["comparator"]): boolean {
  if (comparator === "<") return value < target;
  if (comparator === "<=") return value <= target;
  if (comparator === ">") return value > target;
  if (comparator === ">=") return value >= target;
  return value === target;
}

function quantile(values: number[], probability: number): number | null {
  if (!values.length) return null;
  const position = (values.length - 1) * probability;
  const lower = Math.floor(position);
  const upper = Math.ceil(position);
  const value = lower === upper
    ? values[lower]
    : values[lower] + (position - lower) * (values[upper] - values[lower]);
  return round(value);
}

function sampleStandardDeviation(values: number[]): number | null {
  if (values.length < 2) return null;
  const mean = values.reduce((sum, value) => sum + value, 0) / values.length;
  const variance = values.reduce((sum, value) => sum + (value - mean) ** 2, 0)
    / (values.length - 1);
  return round(Math.sqrt(variance));
}

function empiricalPercentile(values: number[], target: number): number {
  const below = values.filter((value) => value < target).length;
  const equal = values.filter((value) => value === target).length;
  return (below + 0.5 * equal) / values.length;
}

function round(value: number): number {
  return Math.round(value * 1000) / 1000;
}
