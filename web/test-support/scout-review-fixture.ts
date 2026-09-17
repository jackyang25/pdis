import type { Conformity, ContentBlock, Measurement, QuantitativeTarget, ScoutResponse, Variable } from "../lib/api.ts";
import { applyEvidenceReviewRecommendations, reviewQuantitativeCandidateGroup } from "../lib/quantitative-review.ts";

export type ReviewFixtureState = "pending" | "partial" | "completed";
const axes = ["measure", "endpoint", "intervention", "population", "regimen", "time_horizon", "statistic", "conditions"] as const;
const stamp = { org: "bmgf", source_type: "itpp", intervention_class: "vaccine", indication: "malaria" };

function block(id: string, content: string, ordinal: number): ContentBlock {
  return { id, content, ordinal, doc_id: "seed-document", block_type: "paragraph", heading_stack: [], section_label: null, structural_meta: {}, style_hint: {}, image: null };
}

function target(id: string, measure: string, value: number, unit: string, quote: string): QuantitativeTarget {
  const span = { quote, block_ids: [`seed-document/${id}`] };
  return {
    id, expression: { kind: "bound", value, lower: null, upper: null, unit, comparator: ">=" },
    role: "threshold", quote, doc_block_ids: span.block_ids,
    field_links: [{ attribute_ref: id === "target" ? "protective_efficacy" : id, relation: "defines", reason: "Mapped from this source statement." }],
    semantic_profile: Object.fromEntries(axes.map(axis => [axis, { state: axis === "measure" ? "specified" : "not_specified", value: axis === "measure" ? measure : "", other: "" }])) as QuantitativeTarget["semantic_profile"],
    comparison_contract: Object.fromEntries(axes.map(axis => [axis, { mode: axis === "measure" ? "exact" : "unconstrained", scope: axis === "measure" ? measure : "", reason: "" }])) as QuantitativeTarget["comparison_contract"],
    semantic_provenance: { measure: [span], endpoint: [], intervention: [], population: [], regimen: [], time_horizon: [], statistic: [], conditions: [] },
    provenance_spans: [span], ai_recommendation: "confirm", ai_review_reason: "Explicit document commitment.", review_status: "approved",
  };
}

function variable(item: QuantitativeTarget): Variable {
  return {
    name: item.field_links[0].attribute_ref, description: item.semantic_profile.measure.value,
    block_ids: item.doc_block_ids, document_target: item.quote, document_spans: item.provenance_spans,
    definition_mode: "fixed", target_resolved: true, target_resolution_reason: "Resolved from the cited document statement.",
    evidence_domain: "clinical", entities: [], quantitative_target_ids: [item.id], quantitative_statement_dispositions: [],
    quantitative_target_status: "present", quantitative_target_status_reason: "A scalar proposal was mapped from this statement.",
  };
}

function base(targets: QuantitativeTarget[]): ScoutResponse {
  return {
    phase: "target_review", ...stamp,
    context_validation: { status: "match", configured_indication: "malaria", document_indication: "malaria", reason: "The seeded document concerns malaria.", doc_block_ids: targets[0].doc_block_ids },
    quantitative_ledger: {
      status: "complete", reason: "Every numeric statement received a mapping decision.", block_ids: targets.flatMap(item => item.doc_block_ids), targets,
      reviews: targets.map(item => ({ unit_id: `statement-${item.id}`, block_id: item.doc_block_ids[0], quote: item.quote, classification: "target", reason: "Mapped scalar proposal.", attribute_refs: item.field_links.map(link => link.attribute_ref), target_ids: [item.id], review_status: "resolved" })),
    },
    variables: targets.map(variable), matches: [], assessments: [], conformity: [], precedents: [], development_landscape: [], safety_observations: [], search_plan: [],
    stats: { queries: 0, findings: 0, unique_findings: 0, insights: 0, matches: 0, assessments: 0 },
    blocks: targets.map((item, index) => block(item.doc_block_ids[0], item.quote, index)),
  };
}

function candidate(id: string, value: number, source: string, recommendation: Measurement["ai_recommendation"] = "flag"): Measurement {
  return {
    candidate_id: id, expression: { kind: "point_estimate", value, lower: null, upper: null, unit: "%", comparator: "" },
    url: `https://example.test/${source}`, insight_id: `insight-${id}`,
    source_quote: `This fictional source reports protective efficacy of ${value}%. The analysis uses the source population described in this report.`,
    source_record_id: `url:https://example.test/${source}`, source_identity_status: "url_fallback", evidence_unit_id: `url:https://example.test/${source}/unit:record`,
    evidence_unit: { status: "record_level", group: { state: "not_specified", value: "", other: "" }, cohort: { state: "not_specified", value: "", other: "" }, reason: "One source population; repeated estimates are not independent." },
    semantic_assessment: { source_ownership: { state: "yes", reason: "The mapper attributed this result to the source." }, dimensions: Object.fromEntries(axes.map(axis => [axis, { source: { state: axis === "measure" ? "specified" : "not_specified", value: axis === "measure" ? "Protective efficacy" : "", other: "" }, compatibility: { state: "yes", reason: axis === "measure" ? "The source reports protective efficacy, which is the measure required by the target." : "The mapped target imposes no restriction on this field; a match is not required." } }])) as Measurement["semantic_assessment"]["dimensions"] },
    semantic_status: "comparable", semantic_reason: "The mapper found the required measure compatible.", evidence_mode: "prose",
    ai_recommendation: recommendation, ai_review_reason: recommendation === "admit" ? "The independent reviewer recommends admitting this estimate." : recommendation === "reject" ? "The independent reviewer questions whether this mapped result is a direct comparator and recommends rejection." : "The independent reviewer left this estimate for manual review.",
    admission_status: "needs_review", admission_reason: "Prose evidence requires explicit admission.", inclusion_reason: "", exclusion_reasons: ["Prose evidence requires explicit admission."], structural_reasons: [], age_months: null,
  };
}

function attachEvidence(result: ScoutResponse, candidates: Measurement[]): ScoutResponse {
  const item = result.quantitative_ledger.targets[0];
  const score: Conformity = {
    attribute_refs: item.field_links.map(link => link.attribute_ref), target_id: item.id, target_role: item.role, target_value: item.expression.value!, comparator: ">=", unit: item.expression.unit,
    target_label: `${item.semantic_profile.measure.value} >=${item.expression.value}${item.expression.unit}`, target_quote: item.quote,
    target_meeting_count: 0, target_meeting_rate: 0, verdict: "No admitted comparators", benchmark_count: 0,
    benchmark_minimum: null, benchmark_maximum: null, benchmark_mean: null, benchmark_median: null, benchmark_lower_quartile: null, benchmark_upper_quartile: null, benchmark_standard_deviation: null,
    target_percentile: null, ambition_percentile: null, calibration_status: "insufficient", doc_block_ids: item.doc_block_ids,
    measurements: [], excluded_measurements: candidates, source_dispositions: [],
  };
  result.phase = "evidence_review";
  result.conformity = [score];
  result.matches = candidates.map(measurement => ({
    insight: { id: measurement.insight_id, statement: measurement.source_quote, query: "fictional protective efficacy", query_tracks: ["general"], retrieval_target_ids: [item.id], ...stamp, attribute_ref: score.attribute_refs[0],
      supporting_findings: [{ title: `Fictional study: ${measurement.source_record_id.split("/").at(-1)}`, url: measurement.url, query: "fictional protective efficacy", retrieved_at: "2026-09-16T12:00:00Z", published_at: null, excerpt: measurement.source_quote, source: "pubmed" }],
    }, relation: "extends", reason: "An external estimate supplies context for the document target.", doc_block_ids: item.doc_block_ids,
  }));
  const sourceUrls = [...new Set(candidates.map(item => item.url))];
  result.search_plan = [{ attribute_ref: score.attribute_refs[0], lane: "general", query: "fictional protective efficacy", connector: "pubmed", operation: "search", tracks: ["general"], doc_block_ids: item.doc_block_ids, target_ids: [item.id], intent_ids: ["seed-intent"], input_queries: ["fictional protective efficacy"], applicability: "applicable", applicability_reason: "External estimates can inform this target.", status: "complete", error: "", finding_count: candidates.length, source_urls: sourceUrls }];
  result.stats = { queries: 1, findings: candidates.length, unique_findings: sourceUrls.length, insights: candidates.length, matches: candidates.length, assessments: 0 };
  return result;
}

/** Small complete, source-linked evidence fixture used by component regressions. */
export function reviewFixture(phase: "target_review" | "evidence_review" = "evidence_review"): ScoutResponse {
  const result = base([target("target", "Protective efficacy", 80, "%", "Target protective efficacy is at least 80%.")]);
  if (phase === "target_review") {
    result.quantitative_ledger.targets[0].review_status = "needs_review";
    return result;
  }
  const candidates = [candidate("single", 85, "study-single"), candidate("alternative-a", 70, "study-alternatives"), candidate("alternative-b", 90, "study-alternatives")];
  candidates[0].source_quote += " The report describes the study population, analysis plan, and follow-up window in its methods. ".repeat(8) + "End of complete quotation.";
  return attachEvidence(result, candidates);
}

/** Covers confirm/exclude/flag plus unresolved and partially resolved source statements. */
export function targetReviewFixture(state: ReviewFixtureState = "pending"): ScoutResponse {
  const targets = [
    target("target", "Protective efficacy", 80, "%", "Target protective efficacy is at least 80%."),
    target("example_duration", "Protection duration", 12, "months", "Example only: protection lasting at least 12 months; this is not a product commitment."),
    target("working_duration", "Shelf life", 24, "months", "Working shelf-life assumption: at least 24 months; commitment status is under discussion."),
    target("partial_target", "Thermostability duration", 2, "months", "Thermostability target: at least 2 months. The required storage-temperature limit remains unresolved."),
  ];
  targets.forEach(item => { item.review_status = "needs_review"; });
  targets[1].ai_recommendation = "exclude"; targets[1].ai_review_reason = "The independent reviewer identifies an example rather than a commitment.";
  targets[2].ai_recommendation = "flag"; targets[2].ai_review_reason = "Confirm whether the working assumption is an actual product commitment.";
  const result = base(targets);
  const partial = result.quantitative_ledger.reviews[3];
  partial.classification = "partial_target"; partial.review_status = "needs_review"; partial.reason = "The duration was mapped; the unresolved storage limit cannot be used as a numeric target.";
  const unresolved = block("seed-document/unresolved", "The maximum administration volume is still to be determined.", result.blocks.length);
  result.blocks.push(unresolved); result.quantitative_ledger.block_ids.push(unresolved.id);
  result.variables.push({ ...variable(targets[3]), name: "administration_volume", description: "Administration volume", block_ids: [unresolved.id], document_target: unresolved.content, document_spans: [{ quote: unresolved.content, block_ids: [unresolved.id] }], quantitative_target_ids: [], quantitative_target_status: "uncertain", quantitative_target_status_reason: "No scalar volume was resolved." });
  result.quantitative_ledger.reviews.push({ unit_id: "unresolved", block_id: unresolved.id, quote: unresolved.content, classification: "uncertain", reason: "No reliable scalar administration-volume target could be resolved.", attribute_refs: ["administration_volume"], target_ids: [], review_status: "needs_review" });
  result.quantitative_ledger.status = "uncertain";
  if (state !== "pending") {
    targets[0].review_status = "approved"; targets[1].review_status = "rejected";
  }
  if (state === "completed") {
    targets[2].review_status = "rejected"; targets[3].review_status = "approved";
    result.quantitative_ledger.reviews.forEach(review => { if (review.review_status === "needs_review") review.review_status = "accepted_exclusion"; });
  }
  return result;
}

/** Same target, several independent source units; alternatives remain one decision per unit. */
export function evidenceReviewFixture(state: ReviewFixtureState = "pending"): ScoutResponse {
  const result = reviewFixture();
  const items = result.conformity[0].excluded_measurements;
  items[0].ai_recommendation = "admit"; items[0].ai_review_reason = "The independent reviewer recommends admitting this source estimate.";
  items.push(candidate("single-reject", 65, "reviewer-disagrees", "reject"), candidate("single-flag", 75, "manual-review"));
  items.push(candidate("recommended-a", 72, "recommended-choice", "reject"), candidate("recommended-b", 82, "recommended-choice", "admit"));
  items.push(candidate("reject-a", 68, "rejected-choice", "reject"), candidate("reject-b", 78, "rejected-choice", "reject"));
  attachEvidence(result, items);
  if (state !== "pending") result.conformity = applyEvidenceReviewRecommendations(result.conformity);
  if (state === "completed") {
    result.conformity[0] = reviewQuantitativeCandidateGroup(result.conformity[0], ["alternative-a", "alternative-b"], "alternative-b");
    result.conformity[0] = reviewQuantitativeCandidateGroup(result.conformity[0], ["single-flag"], null);
  }
  return result;
}

/** Real diagnostic shapes, kept separate from the standard state/count fixtures. */
export function diagnosticTargetReviewFixture(): ScoutResponse {
  const year = target("approval_year", "Approval year", 2027, "calendar year", "Approval is required by 2027.");
  year.expression.comparator = "<=";
  year.expression.display = { kind: "calendar_year", unit_singular: "", unit_plural: "" };
  const dose = target("dose_count", "Number of doses", 1, "doses", "The regimen requires exactly 1 dose.");
  dose.expression.comparator = "=";
  dose.expression.display = { kind: "quantity", unit_singular: "dose", unit_plural: "doses" };
  dose.ai_recommendation = "unavailable";
  dose.ai_review_failure_code = "independent_review_unavailable";
  dose.ai_review_reason = "The independent review did not complete. No recommendation was returned.";
  for (const item of [year, dose]) item.review_status = "needs_review";
  const result = base([year, dose]);
  const failed = block("seed-document/failed", "The target shelf life is 24 months.", 2);
  result.blocks.push(failed);
  result.quantitative_ledger.block_ids.push(failed.id);
  result.quantitative_ledger.status = "uncertain";
  result.quantitative_ledger.reviews.push({ unit_id: "failed", block_id: failed.id, quote: failed.content, classification: "mapping_failed", failure_code: "invalid_target_mapping", reason: "The proposed mapping failed source validation; no usable numeric target was retained.", attribute_refs: [], target_ids: [], review_status: "needs_review" });
  return result;
}

export function diagnosticEvidenceReviewFixture(): ScoutResponse {
  const item = target("target", "Protective efficacy", 80, "%", "Target protective efficacy is at least 80% in adults during the first 6 months.");
  for (const [axis, value] of [["population", "Adults"], ["time_horizon", "First 6 months"]] as const) {
    item.semantic_profile[axis] = { state: "specified", value, other: "" };
    item.comparison_contract[axis] = { mode: "exact", scope: value, reason: "Required by the document target." };
    item.semantic_provenance[axis] = item.provenance_spans;
  }
  const measurement = candidate("context", 85, "retained-context", "unavailable");
  measurement.ai_review_failure_code = "independent_review_unavailable";
  measurement.ai_review_reason = "The independent review did not complete. Inspect the source and mapping before deciding.";
  measurement.source_passage = `${measurement.source_quote} Participants were adults, followed for the first 6 months. This result excludes the separate adolescent cohort.`;
  for (const [axis, value] of [["population", "Adults"], ["time_horizon", "First 6 months"]] as const) {
    measurement.semantic_assessment.dimensions[axis] = { source: { state: "specified", value, other: "" }, compatibility: { state: "yes", reason: `The retained source passage explicitly states ${value.toLowerCase()}.` } };
  }
  const result = attachEvidence(base([item]), [measurement]);
  result.matches[0].insight.supporting_findings[0].excerpt = measurement.source_passage;
  return result;
}
