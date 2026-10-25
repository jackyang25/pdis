import type { Tone } from "./tone.ts";
export type Header = {
  org: string;
  source_type: string;
  intervention_class: string;
  indication: string;
};

export type ToolName = "chunker" | "aligner" | "screener" | "inspector" | "scout" | "drafter";

export type ContextOption = {
  org: string;
  intervention_class: string;
  supports: Partial<Record<ToolName, boolean>>;
};

export type DocumentType = {
  key: string;
  org: string;
  source_type: string;
  intervention_class: string;
  display_name: string;
  supports: Partial<Record<ToolName, boolean>>;
};

/**
 * The kind of file a block was parsed from, recorded by the parser that read it.
 *
 * Mirrors `SourceFormat` in `services/chunker/formats.py`; `source-chip.test.ts` fails if
 * the two diverge. Absent on a block saved before the parser recorded it, which a reader
 * shows as unknown rather than working out from a page or slide number.
 */
export const SOURCE_FORMATS = ["docx", "pptx", "pdf", "image"] as const;
export type SourceFormat = (typeof SOURCE_FORMATS)[number];

export type ContentBlock = {
  id: string;
  doc_id: string;
  ordinal: number;
  block_type: string;
  content: string;
  heading_stack: string[];
  section_label: string | null;
  structural_meta: Record<string, unknown>;
  style_hint: Record<string, unknown>;
  image?: {
    media_type: string;
    data_base64: string;
    sha256: string;
    source_media_type: string;
    /** The image's own pixel size. Zero when a result predates the field. */
    width?: number;
    height?: number;
  } | null;
  source_format?: SourceFormat | null;
};

/**
 * Inspector's published vocabulary.
 *
 * Mirrors `VERDICTS` in `services/inspector/models.py`; `inspector-vocabulary.test.ts`
 * fails if the two diverge. One axis, where there used to be three stacked over the
 * same fact - a reason, a level looked up from it, and a status that bucketed the
 * levels. Every name here is the one the service uses - no layer invents a
 * synonym, because a second name for one thing is a second thing to keep in step.
 */
export const VERDICTS = [
  "specified",
  "not_present",
  "placeholder",
  "insufficient",
  "vague",
  "section_conflict",
  "not_applicable",
] as const;
export type Verdict = (typeof VERDICTS)[number];

/** The verdicts that name something to fix, in published order. */
export const ASSESSED_VERDICTS: Verdict[] = [
  "not_present",
  "placeholder",
  "insufficient",
  "vague",
  "section_conflict",
];

/** One rubric unit and how it stands: a verdict, a sentence, and its blocks. */
export type Assessment = {
  id: string;
  verdict: Verdict;
  /** What is wrong, in one sentence. Empty exactly when nothing is wrong. */
  statement: string;
  /** Both names set is a variable, section alone is a section, neither is the document. */
  section_name: string | null;
  variable_name: string | null;
  optional: boolean;
  /** Where this was read from. Empty exactly when nothing is there. */
  cited_block_ids: string[];
  /** Worklist position, assigned server-side so every view orders identically. */
  rank: number;
};

export type SectionAssessment = {
  section_name: string;
  is_present: boolean | null;
  /** A deterministic section assignment in document order, not a citation. */
  mapped_block_ids: string[];
  units: Assessment[];
  /** This section's units counted by verdict. Bounded by the rubric. */
  verdict_counts: Record<Verdict, number>;
};

/**
 * Why a model call produced no usable answer. Mirrors `shared.ai.FAILURE_CODES`.
 *
 * Machine-readable, beside the prose a failure also carries, so a reader can tell a
 * cut-off answer from an invalid one without parsing the sentence.
 */
export const FAILURE_CODES = ["response_truncated", "invalid_model_response", "provider_error", "response_refused"] as const;
export type FailureCode = (typeof FAILURE_CODES)[number];

/**
 * What Scout records when a stage obtained no verdict for a subject.
 *
 * Never offered to a model, so it is a processing gap rather than a reading, and it always
 * travels with a `FailureCode`. Mirrors `NOT_ASSESSED` in `services/scout/models.py`.
 */
export const NOT_ASSESSED = "not_assessed" as const;
export type NotAssessed = typeof NOT_ASSESSED;

/**
 * What Scout records when no insight reached a variable, on grounding and both precedent axes.
 *
 * Set by code with no model call and an empty reason, so the interface says it in its own
 * voice. Neither the model's `unknown` (the evidence shown could not be judged) nor
 * `not_assessed` (a stage failed): nothing failed, and no evidence was shown. Mirrors
 * `NO_EVIDENCE` in `services/scout/models.py`.
 */
export const NO_EVIDENCE = "no_evidence" as const;
export type NoEvidence = typeof NO_EVIDENCE;

/**
 * What Scout records for a field the reviewer left out of evidence search at target review,
 * on grounding and both precedent axes.
 *
 * The reviewer's decision, not an observation: no query was planned, so nothing was
 * retrieved or judged. Carries no failure code, no reason and no evidence, and is exactly the
 * fields named in `ScoutResponse.not_searched_fields`. Mirrors `NOT_SEARCHED` in
 * `services/scout/models.py`.
 */
export const NOT_SEARCHED = "not_searched" as const;
export type NotSearched = typeof NOT_SEARCHED;

export type InspectionResult = {
  doc_id: string;
  reviews: InspectionReview[];
  applicability_facts: Record<string, ProductFact>;
  rubric_resolutions: RubricResolution[];
  /** Conflicts spanning sections, which no single unit can own. */
  document_findings: Assessment[];
  consistency_status: "complete" | "partial" | "failed" | "not_applicable" | "unknown";
  /** Why the consistency pass failed; set exactly when its status is `failed`. */
  consistency_failure_code: FailureCode | null;
  /** Whether the run completed. A process fact, never a verdict. */
  assessment_status: "complete" | "unknown";
  org: string | null;
  source_type: string | null;
  intervention_class: string | null;
  indication: string | null;
  // The parsed source document behind the assessments (for the Ask assistant).
  blocks: ContentBlock[];
};

export type ProductFact = "yes" | "no" | "unknown";
export type RubricSource = { id: string; title: string; revision: string; url: string };
export type RequirementSnapshot = {
  id: string; section_name: string; variable_name: string | null;
  description: string; expectations: string; source_refs: string[];
};
export type RubricSnapshot = {
  updated_on: string | null;
  id: string; revision: string | null; display_name: string; authority: string;
  scope: string; evidence_scope: "mapped_section" | "whole_document";
  stage_guidance: string;
  mirrors: string | null;
  /** Library landing page, not a direct source or requirement citation. */
  reference_url?: string | null;
  sources: RubricSource[]; requirements: RequirementSnapshot[];
};
export type InspectionReview = {
  rubric: RubricSnapshot; sections: SectionAssessment[]; assessment_status: "complete";
};
export type RubricResolution = {
  rubric_id: string; display_name: string;
  status: "included" | "outside_review_scope" | "needs_context";
  reason_code: string; reason: string;
};
/** View-only projection. Never stored beside the authoritative run. */
export type InspectionReviewView = Omit<InspectionResult, "reviews" | "rubric_resolutions"> & InspectionReview;

/**
 * What each verdict is called, and separately what it means.
 *
 * Two maps rather than one, after the same failure twice: a single map's values ran to
 * thirteen words because they were written as explanations, and the document trace
 * rendered "The rubric asks for this and the document does not usably supply it" as
 * inline pill text.
 *
 * A label sits beside a value and has to be short. A description explains it where there
 * is room - the how-to-read panel, and a native title on hover.
 *
 * Nothing here names a consequence: what a shortfall costs a programme is not something
 * Inspector can see.
 */
export const VERDICT_LABEL: Record<Verdict, string> = {
  specified: "Specified",
  not_present: "Not present",
  placeholder: "Placeholder",
  insufficient: "Insufficient",
  vague: "Vague",
  // Not "Conflicts" alone: Scout's RELATIONSHIP_LABEL already spends that word on evidence
  // contradicting a target, and one word meaning two things across two tools is the drift
  // the shared-vocabulary test exists to catch. Naming the axis keeps them apart.
  section_conflict: "Section conflict",
  not_applicable: "N/A",
};

export const VERDICT_DESCRIPTION: Record<Verdict, string> = {
  specified: "The rubric asks for this and the document supplies it usably",
  not_present: "Nothing is there",
  placeholder: "A token such as <<TBD>> sits where the value belongs",
  insufficient: "Part of what the requirement asks for is not there",
  vague: "Covered, but unusable as stated - unmeasurable or too general to act on",
  section_conflict: "Another section states something this cannot hold with",
  not_applicable: "The rubric accepts this being absent",
};

/**
 * One tone per verdict. The only place the judgement is made.
 *
 * The pill fills with it, the section's count row dots with it, and the document trace
 * emphasises with it - three shapes, one decision, per the rule in `lib/tone.ts`. It lived
 * on the Inspector page, so the trace decided the same split again from a list of its own.
 *
 * The shortfalls are not graded against each other. `vague` is the one that leaves the
 * requirement covered - the content is all there and unusable - so it reads as caution;
 * the rest leave something absent and read as danger. That split is the vocabulary's own
 * worst-first order, not a severity scale invented here. The tint is applied by
 * `VerdictPill`, which reads the tone directly.
 */
export const VERDICT_TONE: Record<Verdict, Tone> = {
  specified: "success",
  not_present: "danger",
  placeholder: "danger",
  insufficient: "danger",
  vague: "warning",
  section_conflict: "danger",
  not_applicable: "neutral",
};

export function verdictLabel(verdict: string): string {
  return VERDICT_LABEL[verdict as Verdict] ?? verdict;
}

/**
 * Every unit worth acting on, in the order the result already assigned.
 *
 * A view over the sections rather than a second array in the payload. The ranked list
 * used to be computed server-side and published beside the units it duplicated, so the
 * two could disagree; `rank` travels on the unit instead.
 */
export function worklist(inspection: Pick<InspectionReviewView, "sections" | "document_findings">): Assessment[] {
  const fromUnits = (inspection.sections ?? [])
    .flatMap((section) => section.units)
    .filter((unit) => ASSESSED_VERDICTS.includes(unit.verdict));
  return [...fromUnits, ...(inspection.document_findings ?? [])].sort(
    (left, right) => left.rank - right.rank,
  );
}

/**
 * A section's units, counted by the verdicts that need work.
 *
 * `specified` and `not_applicable` are absent because this answers "what needs work
 * here". A section with none returns nothing, which the caller shows as `Specified`.
 */
export function sectionShortfalls(
  section: SectionAssessment,
): Record<Verdict, number> {
  const counts = section.verdict_counts ?? ({} as Record<Verdict, number>);
  return Object.fromEntries(
    ASSESSED_VERDICTS.map((verdict) => [verdict, counts[verdict] ?? 0]),
  ) as Record<Verdict, number>;
}

export type InspectorResponse = {
  inspection: InspectionResult;
};

export type Finding = {
  url: string;
  title: string;
  query: string;
  retrieved_at: string;
  excerpt: string | null;
  published_at: string | null;
  source: string;
  evidence_role?: "evidence" | "reference";
  development_records?: DevelopmentRecord[];
  safety_observations?: SafetyObservationRecord[];
  queries?: string[];
  source_lanes?: string[];
  source_labels?: Record<string, string>;
  source_attributions?: Record<string, SourceAttribution>;
  retrieval_paths?: {
    query: string;
    lane: string;
    connector?: string;
    operation?: string;
  }[];
  title_source_lane?: string;
  excerpt_source_lane?: string;
  published_source_lane?: string;
  /** Identifiers the provider stated, by scheme: doi, pmid, nct, setid, ... */
  identifiers?: Record<string, string>;
  /** The record's identity, `<source>:<provider id>`. */
  record_key?: string;
  /** How much of `published_at` the source stated; a year-only date is not 1 January. */
  published_precision?: "day" | "month" | "year" | "";
  /** Whose words the excerpt is: the source's, its fields labelled by PDIS, or a model's. */
  excerpt_kind?: "passage" | "structured_fields" | "generated";
};

export type DevelopmentRecord = {
  program_name: string;
  record_type: "clinical_trial" | "compound_catalog" | "regulatory_label" | "regulatory_clearance";
  record_id: string;
  sponsor: string;
  phase: string;
  status: string;
  source_role: SourceRole;
};

export type SafetyObservationRecord = {
  product_name: string;
  record_type: "label_warning" | "reported_event" | "device_event" | "recall";
  source_system: "fda_label" | "faers" | "maude" | "fda_recall";
  label: string;
  detail: string;
  report_count: number | null;
  qualification: string;
  source_role: SourceRole;
};

/** One measured quantity for one place in one year, as an adapter normalized it. */

export type SourceRole =
  | "experimental"
  | "comparator"
  | "control"
  | "co_intervention"
  | "unknown";

export type TargetRelationship =
  | "direct"
  | "analogous"
  | "adjacent"
  | "unrelated"
  | "unknown"
  | NotAssessed;

export type SourceAttribution = {
  label: string;
  url: string;
  prefix: string;
};

/**
 * One native request one lane made.
 *
 * `query` is what the provider received, which for a field-addressed source is not the
 * text a reader typed: a typed sentence reaches ClinicalTrials.gov as
 * `condition:<that sentence>`. `returned` counts the request's own findings, before
 * cross-lane deduplication, so lane numbers can exceed the number of findings shown.
 */
export type SearchLane = {
  source: string;
  query: string;
  status: "complete" | "failed" | "skipped";
  /** Why nothing came back: an adapter failure, or why the planner ruled the lane out. */
  detail: string;
  returned: number;
  error_code?: string;
  /** The query the provider reports it ran, where it reports one (PubMed's translation). */
  provider_query?: string;
  warnings?: OutcomeWarning[];
};

export type SearcherResponse = {
  query: string;
  findings: Finding[];
  /** Every request every selected lane made, including the ones that returned nothing. */
  lanes: SearchLane[];
  /** Findings left out by a caller's `max_findings`. The page never sets one, so always 0 here. */
  omitted_findings: number;
};

export type SearchSource = {
  key: string;
  label: string;
  default_enabled: boolean;
  configured: boolean;
  evidence_domains: string[];
  required_entity_types: string[];
  /** What this lane is responsible for, and whose setting it describes. */
  evidence_class: string;
  jurisdiction: string;
  /** Scope dimensions this lane can act on, so a control can say who will use it. */
  reads: string[];
  /** Whether a date bound narrows this lane at the provider, or only after retrieval. */
  honors_date_bound: boolean;
  attribution?: SourceAttribution | null;
};

export type Insight = {
  id?: string;
  statement: string;
  query: string;
  query_tracks?: string[];
  retrieval_target_ids?: string[];
  supporting_findings: Finding[];
  org: string | null;
  source_type: string | null;
  intervention_class: string | null;
  indication: string | null;
  attribute_ref: string | null;
};

export type Match = {
  insight: Insight;
  /** The first four are the model's relation; `not_assessed` carries `failure_code`. */
  relation: "contradicts" | "extends" | "confirms" | "unrelated" | NotAssessed;
  reason: string;
  doc_block_ids?: string[];
  /** Set on exactly the `not_assessed` matches, blank on a verdict. */
  failure_code: FailureCode | "";
};

export type EvidenceStrength =
  | "well_grounded"
  | "partial"
  | "thin"
  | "unsupported"
  | "unknown"
  | NoEvidence
  | NotSearched
  | NotAssessed;

export type EvidenceAssessment = {
  attribute_ref: string;
  strength: EvidenceStrength;
  reason: string;
  doc_target: string;
  doc_block_ids: string[];
  supporting_insight_ids: string[];
  supporting_findings: Finding[];
  /** Set on exactly the `not_assessed` assessments, blank on a verdict. */
  failure_code: FailureCode | "";
};

export type FunnelStats = {
  queries: number;
  findings: number;
  unique_findings: number;
  insights: number;
  matches: number;
  assessments: number;
  /**
   * Announcements read for a program name, how many named one, and how many readings
   * failed.
   *
   * The second alone is unreadable: an announcement naming no program leaves no row in
   * the landscape, so without the attempts a weak reading and a quiet week look
   * identical. A failed reading is counted apart from one that named nothing, because a
   * failure says nothing about the announcement.
   */
  announcements_read: number;
  announcements_named: number;
  announcements_failed: number;
  /** The same failures by code, so a refusal reads apart from an outage. Sums to the above. */
  announcements_failed_by_code: Partial<Record<FailureCode, number>>;
};

/** Something a provider reported about one request, beside its records. */
export type OutcomeWarning = {
  code: "provider_warning" | "provider_error" | "content_unavailable";
  /** What the provider reported, in its words. */
  detail: string;
};

export type SearchTrace = {
  attribute_ref: string;
  lane: string;
  query: string;
  connector?: string;
  operation?: string;
  request_options?: Record<string, string>;
  tracks: string[];
  doc_block_ids: string[];
  target_ids: string[];
  intent_ids: string[];
  input_queries: string[];
  applicability: "applicable" | "not_applicable";
  applicability_reason: string;
  status: "complete" | "failed" | "skipped";
  error: string;
  /** The machine-readable kind of a failed request, beside `error`; blank unless it failed. */
  error_code: string;
  /** The query the provider reports it ran, where it reports one (PubMed's translation). */
  provider_query: string;
  /** What the provider reported beside its records. A complete request may still carry some. */
  warnings: OutcomeWarning[];
  finding_count: number;
  source_urls: string[];
  /**
   * A subset of source_urls the window held out. Undated sources are never here.
   * Optional for the same reason as `ScoutResponse.published_since`: traces in
   * results saved before windows existed do not carry it.
   */
  excluded_before_window?: string[];
};

export type Measurement = {
  expression: NumericExpression;
  candidate_id: string;
  url: string;
  insight_id: string;
  source_quote: string;
  source_passage?: string;
  source_record_id: string;
  source_identity_status: "canonical" | "url_fallback";
  evidence_unit_id: string;
  evidence_unit: EvidenceUnitIdentity;
  semantic_assessment: MeasurementSemanticAssessment;
  semantic_status: "comparable" | "contextual" | "incompatible" | "unknown";
  semantic_reason: string;
  evidence_mode: "prose" | "structured_fact";
  ai_recommendation: "admit" | "reject" | "flag" | "unavailable";
  /** Set on exactly an `unavailable` recommendation: why the independent review gave none. */
  ai_review_failure_code: FailureCode | "";
  ai_review_reason: string;
  admission_status: "needs_review" | "approved" | "rejected" | "not_eligible" | "auto_admitted";
  admission_reason: string;
  inclusion_reason: string;
  exclusion_reasons: string[];
  /**
   * The deterministic half of `exclusion_reasons`, so a check can be told from a judgment.
   *
   * Optional because a result saved before this existed has the two kinds joined into
   * `exclusion_reasons` with no way back; those still render, just without the distinction.
   */
  structural_reasons?: string[];
  age_months: number | null;
};

export type EvidenceUnitIdentity = {
  status: "resolved" | "record_level" | "uncertain";
  group: SemanticSlot;
  cohort: SemanticSlot;
  reason: string;
};

export type TernaryDecision = {
  state: "yes" | "no" | "unknown";
  reason: string;
};

export type MeasurementSemanticAssessment = {
  source_ownership: TernaryDecision;
  dimensions: Record<keyof QuantitativeSemanticProfile, {
    source: SemanticSlot;
    compatibility: TernaryDecision;
  }>;
};

export type SourcePassageDisposition = {
  source_id: string;
  /**
   * The first three are the model's verdict on the source. `not_assessed` is the
   * pipeline reporting that no verdict was obtained, and carries `failure_code`.
   */
  status:
    | "measurements_found"
    | "no_relevant_measurement"
    | "uncertain"
    | "not_assessed";
  reason: string;
  url: string;
  insight_id: string;
  /** Set on exactly a `not_assessed` status, blank on a verdict. */
  failure_code: FailureCode | "";
};

export type Conformity = {
  attribute_refs: string[];
  target_id: string;
  target_role: "threshold" | "optimal" | "other";
  target_value: number;
  comparator: "=" | ">" | ">=" | "<" | "<=";
  unit: string;
  target_label: string;
  target_quote: string;
  target_meeting_count: number;
  /** 0..1 unweighted observed share; null when no comparator was admitted. */
  target_meeting_rate: number | null;
  verdict: string;
  benchmark_count: number;
  benchmark_minimum: number | null;
  benchmark_maximum: number | null;
  benchmark_mean: number | null;
  benchmark_median: number | null;
  benchmark_lower_quartile: number | null;
  benchmark_upper_quartile: number | null;
  benchmark_standard_deviation: number | null;
  target_percentile: number | null;
  ambition_percentile: number | null;
  calibration_status: "insufficient" | "limited" | "sufficient";
  doc_block_ids?: string[];
  measurements: Measurement[];
  excluded_measurements: Measurement[];
  source_dispositions: SourcePassageDisposition[];
};

export type PrecedentLabel =
  | "direct"
  | "adjacent"
  | "none"
  | "unknown"
  | NoEvidence
  | NotSearched
  | NotAssessed;

export type PrecedentSignal = {
  attribute_ref: string;
  precedent: PrecedentLabel;
  /**
   * One classification decides both axes, so a failure leaves both `not_assessed`, a
   * variable no insight reached leaves both `no_evidence`, and one left out at review
   * leaves both `not_searched`.
   */
  outcome: "favorable" | "mixed" | "unfavorable" | "unknown" | NoEvidence | NotSearched | NotAssessed;
  reason: string;
  doc_block_ids: string[];
  coverage_insight_ids: string[];
  outcome_insight_ids: string[];
  supporting_insight_ids: string[];
  supporting_findings: Finding[];
  /** Set on exactly the `not_assessed` signals, blank on a verdict. */
  failure_code: FailureCode | "";
};

export type DevelopmentProgram = {
  projection_id: string;
  name: string;
  source_role: SourceRole;
  target_relationship: TargetRelationship;
  target_relationship_reason: string;
  /** Set on exactly a `not_assessed` relationship, blank on a verdict. */
  target_relationship_failure_code: FailureCode | "";
  sponsors: string[];
  phases: string[];
  statuses: string[];
  record_types: string[];
  record_ids: string[];
  attribute_refs: string[];
  supporting_findings: Finding[];
};

export type SafetyObservation = {
  projection_id: string;
  product_name: string;
  record_type: "label_warning" | "reported_event" | "device_event" | "recall";
  source_system: "fda_label" | "faers" | "maude" | "fda_recall";
  label: string;
  detail: string;
  report_count: number | null;
  qualification: string;
  source_role: SourceRole;
  target_relationship: TargetRelationship;
  target_relationship_reason: string;
  /** Set on exactly a `not_assessed` relationship, blank on a verdict. */
  target_relationship_failure_code: FailureCode | "";
  attribute_refs: string[];
  supporting_findings: Finding[];
};

/**
 * One exact document quotation, and the block it was copied out of.
 *
 * The quote is never typed by a model. It selects a line range and deterministic code
 * copies those lines from the block, which is what lets the trace underline a sentence
 * instead of shading the table around it.
 *
 * Lives here rather than beside the trace that renders it: it is what the API sends,
 * and three wire types spelled the shape out by hand before this existed.
 */
export type DocumentSpan = { quote: string; block_ids: string[] };

/**
 * Every block a set of spans reaches, in order, once each.
 *
 * Derived rather than sent. A finding carrying both its spans and a block list has one
 * fact in two fields, and a reader trusting the citation is trusting them not to
 * disagree. Mirrors `shared.spans.span_block_ids`, which is where the same rule is kept
 * on the service side.
 */
export function spanBlockIds(spans: DocumentSpan[]): string[] {
  return Array.from(new Set(spans.flatMap((span) => span.block_ids)));
}

export type Variable = {
  name: string;
  description: string;
  block_ids?: string[];
  document_target: string;
  document_spans: DocumentSpan[];
  definition_mode: "fixed" | "dynamic";
  target_resolved: boolean;
  target_resolution_reason: string;
  evidence_domain:
    | "general"
    | "biological"
    | "clinical"
    | "safety"
    | "regulatory"
    | "product"
    | "manufacturing"
    | "delivery"
    | "commercial_access";
  /**
   * The run scope dimension this variable's document value supplies (`region` for a
   * target-geography field), or blank. Mirrors `RUN_SCOPE_DIMENSIONS`.
   */
  supplies_scope: RunScopeDimension | "";
  entities: Array<{
    name: string;
    entity_type: string;
    identifier: string;
  }>;
  quantitative_target_ids: string[];
  quantitative_statement_dispositions: QuantitativeStatementDisposition[];
  quantitative_target_status: "not_evaluated" | "present" | "not_applicable" | "uncertain";
  quantitative_target_status_reason: string;
};

export type QuantitativeTarget = {
  id: string;
  expression: NumericExpression;
  role: "threshold" | "optimal" | "other";
  quote: string;
  doc_block_ids: string[];
  field_links: Array<{
    attribute_ref: string;
    relation: "defines" | "constrains" | "context_for";
    reason: string;
  }>;
  semantic_profile: QuantitativeSemanticProfile;
  comparison_contract: Record<keyof QuantitativeSemanticProfile, {
    mode: "exact" | "compatible" | "unconstrained" | "unknown";
    scope: string;
    reason: string;
  }>;
  semantic_provenance: Record<keyof QuantitativeSemanticProfile, DocumentSpan[]>;
  provenance_spans: DocumentSpan[];
  ai_recommendation: "confirm" | "exclude" | "flag" | "unavailable";
  /** Set on exactly an `unavailable` recommendation: why the independent review gave none. */
  ai_review_failure_code: FailureCode | "";
  ai_review_reason: string;
  review_status: "needs_review" | "approved" | "rejected";
};

/**
 * Why a statement's numeric review did not finish. Mirrors
 * `QUANTITATIVE_REVIEW_FAILURE_CODES` in `services/scout/models.py`: the model returned
 * no usable review, or the targets it proposed failed structural validation.
 */
export type QuantitativeReviewFailureCode = "invalid_model_response" | "invalid_target_mapping";

/** The structural checks a proposed target can fail. Mirrors `TARGET_MAPPING_ISSUE_CODES`. */
export const TARGET_MAPPING_ISSUE_CODES = [
  "invalid_target_list",
  "invalid_target_object",
  "missing_field_links",
  "invalid_field_links",
  "invalid_target_expression",
  "target_expression_must_be_bound",
  "invalid_target_role",
  "invalid_target_semantic_profile",
  "invalid_target_comparison_contract",
  "invalid_target_quote",
  "invalid_semantic_provenance",
  "missing_target_provenance",
  "invalid_target_provenance",
  "duplicate_atomic_target",
  "missing_target_mapping",
] as const;
export type TargetMappingIssueCode = (typeof TARGET_MAPPING_ISSUE_CODES)[number];

export type QuantitativeStatementDisposition = {
  quote: string;
  block_ids: string[];
  disposition: "context_only" | "non_scalar" | "range_or_set" | "uncertain" | "mapping_failed";
  failure_code: QuantitativeReviewFailureCode | "";
  /** Which structural checks failed; non-empty exactly on `invalid_target_mapping`. */
  issue_codes: TargetMappingIssueCode[];
  reason: string;
  attribute_refs: string[];
};

export type QuantitativeLedgerReview = {
  unit_id: string;
  block_id: string;
  quote: string;
  classification: "target" | "partial_target" | "context_only" | "non_scalar" | "range_or_set" | "non_numeric" | "uncertain" | "mapping_failed";
  failure_code: QuantitativeReviewFailureCode | "";
  /** Which structural checks failed; non-empty exactly on `invalid_target_mapping`. */
  issue_codes: TargetMappingIssueCode[];
  reason: string;
  attribute_refs: string[];
  target_ids: string[];
  review_status: "resolved" | "needs_review" | "accepted_exclusion";
};

export type QuantitativeLedger = {
  status: "complete" | "not_applicable" | "uncertain";
  reason: string;
  block_ids: string[];
  reviews: QuantitativeLedgerReview[];
  targets: QuantitativeTarget[];
};

export type NumericDisplay = {
  kind: "quantity" | "calendar_year";
  unit_singular: string;
  unit_plural: string;
};

export type NumericExpression = {
  kind: "point_estimate" | "range" | "bound" | "confidence_interval" | "count" | "rate" | "other" | "unknown";
  unit: string;
  value: number | null;
  lower: number | null;
  upper: number | null;
  comparator: "" | "=" | ">" | ">=" | "<" | "<=";
  display?: NumericDisplay;
};

export type SemanticSlot = {
  state: "specified" | "not_specified" | "unknown" | "other";
  value: string;
  other: string;
};

export type QuantitativeSemanticProfile = {
  measure: SemanticSlot;
  endpoint: SemanticSlot;
  intervention: SemanticSlot;
  population: SemanticSlot;
  regimen: SemanticSlot;
  time_horizon: SemanticSlot;
  statistic: SemanticSlot;
  conditions: SemanticSlot;
};

/** Scope dimensions a run states once for every query. Mirrors `RUN_SCOPE_DIMENSIONS`. */
export const RUN_SCOPE_DIMENSIONS = ["condition", "intervention", "region"] as const;
export type RunScopeDimension = (typeof RUN_SCOPE_DIMENSIONS)[number];

/**
 * One scope dimension's value for a run, and where it came from.
 *
 * `unset` carries no value and is a deliberate widening, not a gap; `document` cites the
 * blocks the value was read from, and only it does.
 */
export type ScopeEntry = {
  dimension: RunScopeDimension;
  value: string;
  provenance: "header" | "document" | "config_default" | "unset";
  block_ids: string[];
};

/** What a run searches for. Every dimension has an entry, including the unset ones. */
export type RetrievalScope = { entries: ScopeEntry[] };

/** The identity layers Scout runs, in run order. Mirrors `IDENTITY_LAYERS`. */
export const IDENTITY_LAYERS = ["document_units", "quantitative_targets", "insights", "projections"] as const;
export type IdentityLayer = (typeof IDENTITY_LAYERS)[number];

/**
 * What one identity layer decided about one set, or that it could not decide.
 *
 * `not_reconciled` means the call failed and the set went on unmerged, so duplicates in it
 * may be counted separately; it carries a `FailureCode` and merged nothing. `reconciled`
 * with `merged: 0` is the layer finding nothing to merge, a different claim.
 */
export type IdentityReconciliation = {
  layer: IdentityLayer;
  /** The field name for `insights`; blank for a document-wide or run-wide set. */
  scope: string;
  status: "reconciled" | "not_reconciled";
  /** Members of the set (two or more), and how many were merged into another member. */
  items: number;
  merged: number;
  failure_code: FailureCode | "";
  reason: string;
};

export type ScoutResponse = {
  phase: "target_review" | "evidence_review" | "final";
  org: string;
  source_type: string;
  intervention_class: string;
  indication: string;
  /** ISO date retrieval was scoped to, or "" for none. Every statistic in this
   *  result describes only the evidence that window admitted.
   *
   *  Optional because results saved before windows existed are still readable and
   *  carry no such field - the same reason `search_plan` is optional. A live run
   *  always sends it. */
  published_since?: string;
  context_validation: {
    /** Only `mismatch` stops a run; `not_assessed` means the check obtained no answer. */
    status: "match" | "mismatch" | "uncertain" | NotAssessed;
    configured_indication: string;
    document_indication: string;
    reason: string;
    doc_block_ids: string[];
    /** Set on exactly a `not_assessed` validation, blank on a verdict. */
    failure_code: FailureCode | "";
  };
  /**
   * What the run searches for, resolved before target review and carried on the draft.
   *
   * The continuation reads it back rather than resolving it again, so a draft sent to
   * `continueScout` must keep it: the request is refused without it.
   */
  retrieval_scope: RetrievalScope;
  /** One record per identity call the run made, in the order they ran. */
  reconciliations: IdentityReconciliation[];
  /**
   * Searchable fields the reviewer left out of evidence search at target review.
   *
   * The one statement of that selection: the checkpoint edits it on the draft, the whole
   * draft goes back to `continueScout`, and the final result keeps it. Empty searches every
   * field. Each name holds `not_searched` on grounding and precedent.
   */
  not_searched_fields: string[];
  quantitative_ledger: QuantitativeLedger;
  variables: Variable[];
  search_plan?: SearchTrace[];
  matches: Match[];
  assessments: EvidenceAssessment[];
  conformity: Conformity[];
  precedents: PrecedentSignal[];
  development_landscape: DevelopmentProgram[];
  safety_observations: SafetyObservation[];
  /** Optional so a result saved before this projection existed still loads. */
  stats: FunnelStats;
  // The parsed source document behind the analysis (for the Ask assistant).
  blocks: ContentBlock[];
};

export type AlignmentDocument = {
  doc_id: string;
  source_type: string;
  display_name: string;
};

/**
 * One comparison a run makes.
 *
 * Direction lives here rather than on the document, because a document can sit
 * on either side: with three documents the cTPP is compared against the iTPP and
 * is the reference for the IPDP.
 */
export type AlignmentEdge = {
  edge_id: string;
  reference_doc_id: string;
  comparison_doc_id: string;
  question: string;
};

/**
 * What became of one requirement in the document measured against it.
 *
 * Ordered by distance from the bar, and asymmetric on purpose: `exceeds` and
 * `falls_short` are the same difference read in opposite directions, and the
 * vocabulary this replaced could not tell them apart, so a candidate that beat its
 * target and one that missed it by years carried one label.
 */
export type AlignmentVerdict =
  | "meets"
  | "exceeds"
  | "falls_short"
  | "not_comparable"
  | "not_addressed";

export const ALIGNMENT_VERDICTS: AlignmentVerdict[] = [
  "meets",
  "exceeds",
  "falls_short",
  "not_comparable",
  "not_addressed",
];

/**
 * The tone each alignment verdict carries.
 *
 * `falls_short` and `not_comparable` are caution, not danger: falling short of a target is
 * this tool's central finding and a normal state of an in-progress programme, not a
 * failure. Danger stays with a contradiction or a grade a tool calls blocking, and reusing
 * it here would make one colour mean two things across two tools.
 *
 * `not_addressed` is neutral because nobody has answered yet, which is not a verdict about
 * the answer.
 *
 * One map, read by the count row and by the document trace. The trace's emphasis scale
 * says `caution` where this says `warning` - the same reading under two names - so it
 * translates rather than deciding again.
 */
export const ALIGNMENT_VERDICT_TONE: Record<AlignmentVerdict, Tone> = {
  meets: "success",
  exceeds: "success",
  falls_short: "warning",
  not_comparable: "warning",
  not_addressed: "neutral",
};

export const VERDICT_LABELS: Record<AlignmentVerdict, string> = {
  meets: "Meets",
  exceeds: "Exceeds",
  falls_short: "Falls short",
  not_comparable: "Not comparable",
  not_addressed: "Not addressed",
};

/**
 * One requirement, and what the document being measured does with it.
 *
 * Two citation lists that are not interchangeable: `reference_spans` quote where the bar
 * is stated, `comparison_spans` quote what was read to judge it. The service contract
 * checks each against its own document and against its own text, so resolving either one
 * lands a reader in the file that actually says it, on the line that says it.
 * Per-side visual IDs instead name retained image assets and never claim quoted words.
 */
export type AlignmentFinding = {
  requirement_id: string;
  edge_id: string;
  requirement: string;
  reference_spans: DocumentSpan[];
  verdict: AlignmentVerdict;
  statement: string;
  /** Empty for visual-only evidence or `not_addressed`; the latter cites neither kind. */
  comparison_spans: DocumentSpan[];
  reference_visual_block_ids: string[];
  comparison_visual_block_ids: string[];
};

/** Both citation kinds reach blocks; only text spans claim exact quoted words. */
export function alignmentBlockIds(finding: AlignmentFinding, side: "reference" | "comparison"): string[] {
  return [...new Set([
    ...spanBlockIds(finding[`${side}_spans`]),
    ...finding[`${side}_visual_block_ids`],
  ])];
}

/** One comparison Aligner declares, by document type, before any run. */
export type AlignmentEdgeSpec = {
  reference: string;
  comparison: string;
  question: string;
  /**
   * The document type whose presence makes this comparison redundant.
   *
   * The declared comparisons form a chain, and a chain is broken when its middle
   * document is not supplied. An edge carrying this stands in for the missing link. An
   * iTPP and an IPDP with no cTPP between them compare directly; the same two with a
   * cTPP present do not, because the two-step chain already explains those differences.
   */
  when_absent?: string | null;
};

/**
 * Whether a declared comparison is one these document types make.
 *
 * Mirrors `services.aligner.models.edge_applies`. Both sides need it - the service to
 * build a run, the picker to say what a run would compare before making one - and the
 * preview promising a comparison the run then skips is the failure this prevents.
 */
export function edgeApplies(edge: AlignmentEdgeSpec, chosen: string[]): boolean {
  return (
    chosen.includes(edge.reference) &&
    chosen.includes(edge.comparison) &&
    !(edge.when_absent && chosen.includes(edge.when_absent))
  );
}

/**
 * Identified documents, the comparisons they resolve, their parsed source, and findings.
 *
 * `findings` is the denominator as well as the content: every requirement read out of a
 * reference document appears exactly once whatever its verdict, so two runs of one pair
 * compare line by line and no count is stored beside the list it summarises.
 */
export type AlignmentResult = {
  documents: AlignmentDocument[];
  edges: AlignmentEdge[];
  org: string;
  intervention_class: string;
  indication: string;
  blocks: ContentBlock[];
  findings: AlignmentFinding[];
};

export type AlignerResponse = { alignment: AlignmentResult };

// --- Priority reading -------------------------------------------------------

/** One thing worth a reader's attention first, pointing at findings by ID. */
export type PriorityPoint = {
  title: string;
  statement: string;
  /** IDs of findings in the result the card was read from. */
  finding_ids: string[];
};

/**
 * An AI reading of a finished result: what it amounts to, and where to look first.
 *
 * Derived when a result is opened and held for the session only, so it is never part of
 * a result and never exported.
 */
export type PriorityReading = {
  summary: string;
  points: PriorityPoint[];
};

export type PriorityReadingRequest = {
  authority: string;
  focus: string;
  findings: Array<{
    id: string;
    subject: string;
    group: string;
    verdicts: string[];
    statements: string[];
    notes: string[];
    quote: string;
  }>;
  org: string;
  intervention_class: string;
  indication: string;
};

export async function fetchPriorityReading(
  request: PriorityReadingRequest,
): Promise<PriorityReading> {
  return jsonRequest<PriorityReading>("/api/assistant/priorities", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
}

// --- Screener ------------------------------------------------------------------

/** One declared stage gate, for a selector that has not chosen one yet. */
export type GateSpec = {
  id: string;
  label: string;
  ordinal: number;
};

/**
 * What became of one gate question. Four values, each traceable.
 *
 * `not_applicable` means the question's own text states a class this run is not, so
 * no model read it and it is not a shortfall. `answered`, `partly_answered` and
 * `not_found` are what a model concluded from the material supplied.
 *
 * `not_found` rather than `absent`: "not found in what was supplied" is what the run
 * establishes, whatever anyone expected the documents to hold.
 *
 * There were five states; two of them rested on a judgment about which document
 * could answer a question, which the source question bank does not contain.
 */
export type QuestionState =
  | "not_applicable"
  | "answered"
  | "partly_answered"
  | "not_found";

/** What each state is called where a reader sees it. */
export const QUESTION_STATE_LABEL: Record<QuestionState, string> = {
  answered: "Answered",
  partly_answered: "Partly answered",
  not_found: "Not found",
  not_applicable: "N/A",
};

export const QUESTION_REQUIREMENT_LABEL: Record<QuestionAssessment["requirement"], string> = {
  required: "Required",
  anticipatory: "Anticipatory",
};

/**
 * One tone per question state, on the shared scale.
 *
 * It lived in `screener-coverage-strip.tsx` as hand-written background classes, which
 * made it a fifth tone vocabulary beside the four the scale already holds - and it was
 * unreachable from the metrics row, which is why Screener's counts were the only ones
 * with no dot beside them.
 *
 * `not_found` is `neutral`, matching Aligner's `not_addressed`: both say the material is
 * silent on the subject, and silence is not a failure. Its own comment said so - "the
 * strongest mark, because it is the actionable one, not because it is a failure" - and a
 * danger tone would have made exactly the claim it was refusing.
 */
export const QUESTION_STATE_TONE: Record<QuestionState, Tone> = {
  answered: "success",
  partly_answered: "warning",
  not_found: "neutral",
  not_applicable: "neutral",
};

export type QuestionAssessment = {
  id: string;
  text: string;
  state: QuestionState;
  /**
   * Whether this gate requires the question answered now, or expects it to be forming.
   *
   * From the bank, on every question. It is what makes a count actionable: an unanswered
   * `required` question holds a gate up, and an unanswered `anticipatory` one is early
   * warning rather than a shortfall.
   */
  requirement: "required" | "anticipatory";
  statement: string;
  /**
   * What a partial answer still leaves open, and empty on every other state.
   *
   * A required field on `partly_answered` rather than a sentence folded into
   * `statement`, because this is what a PPL takes back to the grantee — left to prose
   * it was usually there and never guaranteed.
   */
  missing: string;
  cited_block_ids: string[];
};

export type DisciplineReview = {
  id: string;
  label: string;
  questions: QuestionAssessment[];
};

export type ReviewDocument = {
  doc_id: string;
};

/**
 * One gate's triage.
 *
 * Every question the gate asks is here with a state, so the denominator never
 * shrinks and two runs on one gate compare line by line. Counts are derived by
 * readers and never carried: a stored count is a second authority that can
 * disagree with the list it summarises.
 */
export type GateReview = {
  gate_id: string;
  gate_label: string;
  /**
   * The authored question bank this triage transcribes, with its version.
   *
   * Carried on the result rather than looked up, so a downloaded review states its
   * own authority — a reader cannot otherwise tell a v5 triage from a v6 one.
   */
  bank_source: string;
  documents: ReviewDocument[];
  disciplines: DisciplineReview[];
  org: string;
  intervention_class: string;
  indication: string;
  blocks: ContentBlock[];
};

export type ScreenerResponse = { review: GateReview };

export type StageProgress = { completed: number; total: number };
export type StageEvent = { event: "stage"; name: string; completed?: number; total?: number };

/**
 * The stage a run reports while waiting for one of the gateway's bounded run
 * slots. It belongs to no tool's step list, so a progress display has to
 * recognize it rather than resolve it; `api/streaming.py` owns the value.
 */
export const QUEUED_STAGE = "queued";
export type CompleteEvent<T> = { event: "complete"; result: T };
export type ErrorEvent = { event: "error"; detail: string };
export type StreamEvent<T> = StageEvent | CompleteEvent<T> | ErrorEvent;

const configuredApiUrl = process.env.NEXT_PUBLIC_PDIS_API_URL?.replace(/\/+$/, "");
const configuredApiHost = process.env.NEXT_PUBLIC_PDIS_API_HOST?.trim();

/**
 * Where requests go when nothing is configured.
 *
 * Empty string in a production build, which makes every call relative and so
 * same-origin: the deployed client and gateway share one hostname, and the
 * ingress routes `/api/*` to the gateway. That is the only default that can be
 * correct without knowing the deployment's hostname.
 *
 * `NEXT_PUBLIC_*` values are inlined by Next.js at build time, not read at
 * runtime, so a hostname baked in here is fixed for the life of the image. That
 * is why the production default must not be a literal host: setting one at
 * runtime would be ignored, and the previous `http://localhost:8000` default
 * shipped in the browser bundle and failed in the user's browser with nothing
 * in any server log to explain it.
 *
 * Local development keeps the explicit fallback, because there the client is on
 * :3000 and the gateway on :8000 and relative calls cannot reach it.
 */
const unconfiguredApiBase =
  process.env.NODE_ENV === "production" ? "" : "http://localhost:8000";

export const API_BASE =
  configuredApiUrl ||
  (configuredApiHost ? `https://${configuredApiHost}` : unconfiguredApiBase);

/**
 * `fetch`, with a failure to reach the server said in words.
 *
 * The browser's own message for a refused connection, a dropped network or a blocked
 * origin is "Failed to fetch", which a reader cannot act on.
 */
async function reach(input: string, init?: RequestInit): Promise<Response> {
  try {
    return await fetch(input, init);
  } catch (error) {
    if (error instanceof TypeError) {
      throw new Error("Could not reach the PDIS server. Check your connection and try again.");
    }
    throw error;
  }
}

/**
 * What a refused request says, in the server's words.
 *
 * FastAPI sends `{"detail": "..."}`, or for a malformed request a list of `{msg}`. The body
 * was shown as it came, so a reader saw `{"detail":"Unsupported file type"}` - JSON where
 * a sentence belonged.
 */
export async function responseError(res: Response, fallback = "Request failed"): Promise<Error> {
  const text = await res.text().catch(() => "");
  let detail: unknown = text;
  try {
    detail = (JSON.parse(text) as { detail?: unknown }).detail ?? text;
  } catch {
    // Not JSON: a proxy's page or plain text, said as it came.
  }
  const message = Array.isArray(detail)
    ? detail.map((item) => (item && typeof item === "object" && "msg" in item ? String(item.msg) : String(item))).join("; ")
    : typeof detail === "string" ? detail.trim() : "";
  return new Error(message || `${fallback} (${res.status})`);
}

async function jsonRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await reach(`${API_BASE}${path}`, init);
  if (!res.ok) throw await responseError(res);
  return res.json() as Promise<T>;
}

/**
 * Consume an NDJSON stream from a POST. Each line is a `StreamEvent<T>`.
 * Calls `onStage` for each stage event; returns the result from the complete event.
 */
async function streamRequest<T>(
  path: string,
  body: BodyInit,
  onStage?: (stage: string, progress?: StageProgress) => void,
  headers?: HeadersInit,
): Promise<T> {
  const res = await reach(`${API_BASE}${path}`, { method: "POST", body, headers });
  if (!res.ok || !res.body) throw await responseError(res);
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  // Text after the last newline seen. Only each new chunk is searched for line breaks:
  // rescanning the held text from its start after every chunk made a final event of
  // several megabytes - a result with retained images - quadratic to read.
  let partial = "";
  let result: T | null = null;
  let error: string | null = null;

  function handle(line: string) {
    if (!line.trim()) return;
    const event = JSON.parse(line) as StreamEvent<T>;
    if (event.event === "stage") {
      const progress =
        event.completed != null && event.total != null
          ? { completed: event.completed, total: event.total }
          : undefined;
      onStage?.(event.name, progress);
    } else if (event.event === "complete") {
      result = event.result;
    } else if (event.event === "error") {
      error = event.detail;
    }
  }

  while (true) {
    let chunk: ReadableStreamReadResult<Uint8Array>;
    try {
      chunk = await reader.read();
    } catch (failure) {
      // A connection that broke mid-stream - a network drop, a sleeping laptop, a proxy
      // reset - is the same observation as a stream that closed early, so it takes the
      // same sentence below. The browser's own text for it was "network error".
      if (failure instanceof TypeError) break;
      throw failure;
    }
    const { value, done } = chunk;
    if (done) break;
    const text = decoder.decode(value, { stream: true });
    const lastBreak = text.lastIndexOf("\n");
    if (lastBreak === -1) {
      partial += text;
      continue;
    }
    const lines = (partial + text.slice(0, lastBreak)).split("\n");
    partial = text.slice(lastBreak + 1);
    lines.forEach(handle);
  }
  // Whatever the decoder still holds, and a last event the stream closed without ending.
  handle(partial + decoder.decode());

  if (error) throw new Error(error);
  if (result === null) {
    // The stream closed without a `complete` event. The cause is not knowable
    // from here: an allocation reclaimed by the host, a deploy, a dropped
    // connection and a proxy timeout are the same observation to this reader.
    // So this says what happened and what to do, and does not name a cause it
    // would be guessing at.
    //
    // Worth being clear rather than terse: a run costs the reader up to half an
    // hour, and the previous text ("Stream ended without complete event")
    // reached the screen verbatim and told them neither that the work was lost
    // nor that trying again was the fix.
    //
    // Says nothing about what to re-run, because this is reached from seven
    // calls and they do not lose the same thing. A first run has produced
    // nothing, so the document is the starting point. `continueScout` is the
    // second half of a run whose draft and completed review checkpoint the
    // client still holds, so telling that reader to start again from the
    // document would throw away work they had already done. What is true
    // everywhere is that this attempt produced nothing and changed nothing.
    throw new Error(
      "The run stopped before it finished and produced no result. " +
        "Nothing already on screen was changed. Try again.",
    );
  }
  return result;
}

export async function fetchDocumentTypes(): Promise<DocumentType[]> {
  const res = await jsonRequest<{ document_types: DocumentType[] }>(
    "/api/configs/document-types",
  );
  return res.document_types;
}

export async function fetchContexts(): Promise<ContextOption[]> {
  const res = await jsonRequest<{ contexts: ContextOption[] }>(
    "/api/configs/contexts",
  );
  return res.contexts;
}

export type InspectorFactField = {
  key: string; label: string; description: string; options: ProductFact[]; required: boolean;
};
export async function fetchInspectorConfiguration(header: Pick<Header, "org" | "source_type" | "intervention_class">): Promise<{ applicability_facts: InspectorFactField[] }> {
  return jsonRequest(`/api/configs/inspector?${new URLSearchParams(header)}`);
}

export async function fetchIndications(intervention: string): Promise<string[]> {
  const res = await jsonRequest<{ indications: string[] }>(
    `/api/configs/indications?intervention=${encodeURIComponent(intervention)}`,
  );
  return res.indications;
}

function appendHeader(form: FormData, header: Header) {
  form.append("org", header.org);
  form.append("source_type", header.source_type);
  form.append("intervention_class", header.intervention_class);
  form.append("indication", header.indication);
}

export async function runChunker(
  file: File,
  header: Header,
  onStage?: (stage: string) => void,
): Promise<{ doc_id: string; blocks: ContentBlock[] }> {
  const form = new FormData();
  form.append("file", file);
  appendHeader(form, header);
  return streamRequest("/api/chunker/run", form, onStage);
}

export async function runInspector(
  file: File,
  header: Header,
  onStage?: (stage: string, progress?: StageProgress) => void,
  applicabilityFacts: Record<string, ProductFact> = {},
): Promise<InspectorResponse> {
  const form = new FormData();
  form.append("file", file);
  appendHeader(form, header);
  form.append("applicability_facts", JSON.stringify(applicabilityFacts));
  return streamRequest("/api/inspector/run", form, onStage);
}

export async function runSearcher(
  query: string,
  sources: string[],
  // The rest of the one request every lane unpacks its own part of. Blank condition means
  // the adapter falls back to the query text; no entities means the sources that address
  // their API by a named subject have no subject to name.
  facets: {
    condition?: string;
    intervention?: string;
    entities?: string;
    product?: string;
    population?: string;
    region?: string;
    publishedSince?: string;
    outcome?: string;
  } = {},
  onStage?: (stage: string) => void,
): Promise<SearcherResponse> {
  const form = new FormData();
  form.append("query", query);
  form.append("sources", sources.join(","));
  form.append("condition", facets.condition ?? "");
  form.append("intervention", facets.intervention ?? "");
  form.append("entities", facets.entities ?? "");
  form.append("product", facets.product ?? "");
  form.append("population", facets.population ?? "");
  form.append("outcome", facets.outcome ?? "");
  form.append("region", facets.region ?? "");
  form.append("published_since", facets.publishedSince ?? "");
  return streamRequest("/api/searcher/run", form, onStage);
}

export async function fetchSearchSources(): Promise<SearchSource[]> {
  return jsonRequest<SearchSource[]>("/api/searcher/sources");
}

/**
 * `publishedSince` is Scout's own retrieval window, not part of the shared
 * `Header`: only this tool searches externally, so putting it there would hand a
 * field to three tools that cannot act on it.
 */
export async function runScout(
  files: File[],
  header: Header,
  options?: { publishedSince?: string },
  onStage?: (stage: string, progress?: StageProgress) => void,
): Promise<ScoutResponse> {
  const form = new FormData();
  for (const file of files) {
    form.append("files", file);
  }
  appendHeader(form, header);
  form.append("published_since", options?.publishedSince ?? "");
  return streamRequest("/api/scout/run", form, onStage);
}

export async function continueScout(
  draft: ScoutResponse,
  onStage?: (stage: string, progress?: StageProgress) => void,
): Promise<ScoutResponse> {
  return streamRequest(
    "/api/scout/continue",
    JSON.stringify({ draft }),
    onStage,
    { "Content-Type": "application/json" },
  );
}

/**
 * The comparisons Aligner declares.
 *
 * Fetched rather than mirrored here: the service config is the one place that
 * decides what compares to what, and a copy in TypeScript would be a second
 * answer that could disagree with it.
 */
export async function fetchAlignerEdges(): Promise<AlignmentEdgeSpec[]> {
  const data = await jsonRequest<{ edges: AlignmentEdgeSpec[] }>("/api/aligner/edges");
  return data.edges;
}

export async function runAligner(
  documents: { file: File; sourceType: string }[],
  configuration: {
    org: string;
    intervention_class: string;
    indication: string;
  },
  onStage?: (stage: string, progress?: StageProgress) => void,
): Promise<AlignerResponse> {
  const form = new FormData();
  // Parallel lists, paired by position: how many documents a run takes is
  // Aligner's configuration to decide, so neither this function nor the route
  // names them.
  documents.forEach(({ file, sourceType }) => {
    form.append("files", file);
    form.append("source_types", sourceType);
  });
  Object.entries(configuration).forEach(([key, value]) => form.append(key, value));
  return streamRequest("/api/aligner/run", form, onStage);
}

/**
 * The gates Screener can review for this org and intervention.
 *
 * Filtered by intervention on the service side, because a bank is written for the
 * modalities it names — the current ones derive from a drug milestone dictionary and ask
 * about synthetic routes and salt forms. So a modality no bank covers offers no gate,
 * which is the honest thing to show at the point of choosing.
 */
export async function fetchScreenerGates(
  org: string,
  interventionClass: string,
): Promise<GateSpec[]> {
  const data = await jsonRequest<{ gates: GateSpec[] }>(
    `/api/screener/gates?org=${encodeURIComponent(org)}`
      + `&intervention=${encodeURIComponent(interventionClass)}`,
  );
  return data.gates;
}

/** Read the complete document collection against one gate question bank. */
export async function runScreener(
  documents: File[],
  configuration: {
    gate: string;
    org: string;
    intervention_class: string;
    indication: string;
  },
  onStage?: (stage: string, progress?: StageProgress) => void,
): Promise<ScreenerResponse> {
  const form = new FormData();
  documents.forEach((file) => form.append("files", file));
  Object.entries(configuration).forEach(([key, value]) => form.append(key, value));
  return streamRequest("/api/screener/run", form, onStage);
}

// --- Drafter: suggested iTPP targets, reviewed in the browser ---
// Mirrors `services/drafter/models.py`; `result-contracts.ts` checks what a saved draft holds.

export type DraftBasis = "comparable_product" | "published_guidance";
export type DraftSuggestionKind = "range" | "statement" | "insufficient";
export type DraftLeansOn = "comparable_products" | "guidance" | "both";

export type DraftObservation = {
  id: string;
  basis: DraftBasis;
  url: string;
  title: string;
  source_label: string;
  product: string;
  measure: string;
  quote: string;
  /** `text` is the quote's own words for the number, which code checked are in the quote. */
  value: { value: number | null; lower: number | null; upper: number | null; unit: string; text: string } | null;
  numeric_eligible: boolean;
  /** The first day the source's stated date allows; null where it stated none. */
  published_at: string | null;
  published_precision: "day" | "month" | "year" | "";
};

export type DraftGroupSummary = {
  unit: string;
  /** The observations this group's values came from, so a figure can be traced to its quotes. */
  observation_ids: string[];
  count: number;
  minimum: number;
  maximum: number;
  median: number;
  lower_quartile: number;
  upper_quartile: number;
};

export type DraftSuggestion = {
  kind: DraftSuggestionKind;
  minimum: string;
  preferred: string;
  statement: string;
  rationale: string;
  /** Blank only for insufficient evidence. */
  leans_on: DraftLeansOn | "";
  basis_ids: string[];
};

export type DraftVariable = {
  name: string;
  label: string;
  description: string;
  evidence_domain: string;
  status: "complete" | "failed";
  failure: {
    code: "search_planning_failed" | "evidence_unavailable" | "suggestion_failed";
    message: string;
    /** Why the call failed; null only for `evidence_unavailable`, which no call raised. */
    cause: FailureCode | null;
  } | null;
  observations: DraftObservation[];
  statistics: DraftGroupSummary[];
  suggestion: DraftSuggestion | null;
  unread_findings: number;
  /** Quotes a reader offered that their excerpt does not contain, so were not kept. */
  unverified_quotes: number;
};

export type DraftResult = {
  org: string;
  source_type: string;
  intervention_class: string;
  indication: string;
  display_name: string;
  sources: string[];
  /** Sources every request to which failed: their evidence is missing from the whole run. */
  failed_sources: string[];
  /** Sources this deployment has not configured, so they were never asked. */
  unconfigured_sources: string[];
  /** The provider's message for every source that failed at least once. */
  source_errors: { source: string; message: string }[];
  variables: DraftVariable[];
};

export type DrafterResponse = { result: DraftResult };

/** Suggest a target for every iTPP variable of the configured product type. */
export async function runDrafter(
  configuration: { org: string; intervention_class: string; indication: string },
  onStage?: (stage: string, progress?: StageProgress) => void,
): Promise<DrafterResponse> {
  const form = new FormData();
  Object.entries(configuration).forEach(([key, value]) => form.append(key, value));
  return streamRequest("/api/drafter/run", form, onStage);
}

/**
 * A final draft as a Word table; the server refuses a draft still in review.
 *
 * The server names the file, so the browser never restates a document extension.
 */
export async function exportDrafterDocx(result: DraftResult): Promise<{ blob: Blob; filename: string }> {
  const res = await reach(`${API_BASE}/api/drafter/export`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ result }),
  });
  if (!res.ok) throw await responseError(res, "Export failed");
  const named = /filename="([^"]+)"/.exec(res.headers.get("Content-Disposition") ?? "");
  return { blob: await res.blob(), filename: named?.[1] ?? "pdis-drafter" };
}

// --- Ask: read-only, grounded chat over any result object ---
export type AskMessage = { role: "user" | "assistant"; content: string };

export type AssistantContext = {
  filename: string;
  doc_id: string;
  blocks: ContentBlock[];
};

export async function uploadAssistantContext(file: File): Promise<AssistantContext> {
  const form = new FormData();
  form.append("file", file);
  return jsonRequest<AssistantContext>("/api/assistant/context", {
    method: "POST",
    body: form,
  });
}
