export type Header = {
  org: string;
  source_type: string;
  intervention_class: string;
  indication: string;
};

export type ToolName = "chunker" | "aligner" | "expert" | "inspector" | "scout";

export type DocumentType = {
  key: string;
  org: string;
  source_type: string;
  intervention_class: string;
  display_name: string;
  supports: Record<ToolName, boolean>;
};

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
  } | null;
};

/**
 * Inspector's published vocabulary.
 *
 * Mirrors `FINDING_REASONS`, `FINDING_LEVELS`, and `UNIT_STATUSES` in
 * `services/inspector/models.py`; `inspector-vocabulary.test.ts` fails if the two
 * diverge. Every name here is the one the service uses - no layer invents a
 * synonym, because a second name for one thing is a second thing to keep in step.
 */
export const FINDING_REASONS = [
  "missing",
  "placeholder",
  "unmet",
  "off_template",
  "unclear",
  "conflicting",
] as const;
export type FindingReason = (typeof FINDING_REASONS)[number];

export const FINDING_LEVELS = ["not_met", "could_be_stronger"] as const;
export type FindingLevel = (typeof FINDING_LEVELS)[number];

export const UNIT_STATUSES = [
  "met",
  "could_be_stronger",
  "not_met",
  "not_applicable",
] as const;
export type UnitStatus = (typeof UNIT_STATUSES)[number];

/** One thing to fix: one statement, one recommendation, one reason. */
export type RubricFinding = {
  id: string;
  reason: FindingReason;
  statement: string;
  recommendation: string;
  /** Both names set is a variable, section alone is a section, neither is the document. */
  section_name: string | null;
  variable_name: string | null;
  /** Where this was read from. Empty exactly when nothing is there. */
  cited_block_ids: string[];
  /** Worklist position, assigned server-side so every view orders identically. */
  rank: number;
  level: FindingLevel;
};

/** One rubric unit. `status` is derived from the findings beneath it. */
export type UnitAssessment = {
  variable_name: string | null;
  optional: boolean;
  findings: RubricFinding[];
  status: UnitStatus;
};

export type SectionAssessment = {
  section_name: string;
  is_present: boolean;
  /** A deterministic section assignment in document order, not a citation. */
  mapped_block_ids: string[];
  units: UnitAssessment[];
  /** This section's units counted by status. Bounded by the rubric. */
  status_counts: Record<UnitStatus, number>;
};

export type InspectionResult = {
  doc_id: string;
  sections: SectionAssessment[];
  /** Conflicts spanning sections, which no single unit can own. */
  document_findings: RubricFinding[];
  consistency_status: "complete" | "partial" | "failed" | "not_applicable" | "unknown";
  /** Whether the run completed. A process fact, never a finding. */
  assessment_status: "complete" | "unknown";
  org: string | null;
  source_type: string | null;
  intervention_class: string | null;
  indication: string | null;
  // The parsed source document behind the findings (for the Ask assistant).
  blocks: ContentBlock[];
};

/**
 * What each name means, in the reader's words.
 *
 * One map per vocabulary, read through a lookup rather than branched on, so a
 * value added upstream renders as itself instead of failing to compile. Nothing
 * here names a consequence: what a shortfall costs a programme is not something
 * Inspector can see.
 */
export const REASON_LABELS: Record<FindingReason, string> = {
  missing: "Not present",
  placeholder: "Placeholder left in",
  unmet: "Does not meet the requirement",
  off_template: "Off template",
  unclear: "Not specific enough",
  conflicting: "Conflicts with another section",
};

/**
 * What a unit's status is called, and separately what it means.
 *
 * These were one map, whose values ran to thirteen words because they were written as
 * explanations. Inspector's page kept its own short forms for the pill and used the long
 * ones as a tooltip, which worked there; the document trace could not reach the short forms,
 * so it rendered "The rubric asks for this and the document does not usably supply it" as
 * inline pill text.
 *
 * A label sits beside a value and has to be short. A description explains it on hover and
 * has room. Naming both makes which is which a decision rather than an accident.
 */
export const STATUS_LABEL: Record<UnitStatus, string> = {
  met: "Met",
  could_be_stronger: "Could be stronger",
  not_met: "Not met",
  not_applicable: "N/A",
};

export const STATUS_DESCRIPTION: Record<UnitStatus, string> = {
  met: "Meets the rubric",
  could_be_stronger: "Supplied and usable, but could be stronger",
  not_met: "The rubric asks for this and the document does not usably supply it",
  not_applicable: "The rubric accepts this being absent",
};

/**
 * A finding's level.
 *
 * Every level is also a unit status, so the words come from there. Two maps holding "Not
 * met" is how one of them comes to say "Not Met".
 */
export const LEVEL_LABELS: Record<FindingLevel, string> = {
  not_met: STATUS_LABEL.not_met,
  could_be_stronger: STATUS_LABEL.could_be_stronger,
};

export function reasonLabel(reason: string): string {
  return REASON_LABELS[reason as FindingReason] ?? reason;
}

/** The two levels a reader can act on, in published order. */
export const SHORTFALL_LEVELS: FindingLevel[] = ["not_met", "could_be_stronger"];

/**
 * Every finding worth acting on, in the order the result already assigned.
 *
 * A view over the sections rather than a second array in the payload. The ranked
 * list used to be computed server-side and published beside the units it
 * duplicated, so the two could disagree; `rank` travels on the finding instead.
 */
export function worklist(inspection: InspectionResult): RubricFinding[] {
  const fromUnits = (inspection.sections ?? [])
    .flatMap((section) => section.units)
    .filter((unit) => unit.status !== "not_applicable")
    .flatMap((unit) => unit.findings);
  return [...fromUnits, ...(inspection.document_findings ?? [])].sort(
    (left, right) => left.rank - right.rank,
  );
}

/** How many units of a section fall at each level, for its collapsed header. */
export function sectionShortfalls(
  section: SectionAssessment,
): Record<FindingLevel, number> {
  return {
    not_met: section.status_counts?.not_met ?? 0,
    could_be_stronger: section.status_counts?.could_be_stronger ?? 0,
  };
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
  indicator_records?: IndicatorRecord[];
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
export type IndicatorRecord = {
  indicator_code: string;
  indicator_name: string;
  place: string;
  spatial_type: string;
  year: number;
  value: number | null;
  value_text: string;
  parent_place: string;
};

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
  | "unknown";

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
};

export type SearcherResponse = {
  query: string;
  findings: Finding[];
  /** Every request every selected lane made, including the ones that returned nothing. */
  lanes: SearchLane[];
};

/* --- Archivist ---------------------------------------------------------------
 *
 * Archivist reports what the archive says, so there is no verdict, score, or comparison
 * on the wire and nothing here for a component to render as a judgment.
 *
 * The nesting is the contract, not a convenience: a column, then the document types under
 * it, then three disjoint states. Flattening it in a component would let an iTPP's
 * class-level ambition sit in one list beside a cTPP's candidate commitment, and the
 * shape is what makes that unrepresentable rather than merely discouraged.
 */

export type ArchivistColumn = {
  attribute: string;
  /** Non-empty exactly when the column is filterable; its presence is the permission. */
  tags: string[];
  /** The unit family, empty when the column is not a quantity. */
  quantity: string;
  /** Sibling attributes the extraction was fenced against. */
  not_confused_with: string[];
};

export type ArchivistDocument = {
  id: string;
  title: string;
  org: string;
  intervention_class: string;
  indication: string;
  source_type: string;
};

export type ArchivistRecord = {
  document_id: string;
  attribute: string;
  status: string;
  bound: string;
  stated: string;
  magnitude: number | null;
  unit: string;
  tags: string[];
  condition_attribute: string;
  condition_stated: string;
  /** The verbatim span, its block, and that block's whole text - all three, because a
   * quote without its surroundings misleads. */
  quote: string;
  block_id: string;
  block_text: string;
  section_label: string;
  /** Why the document was read as silent, or why the reading is uncertain. */
  reason: string;
};

export type ArchivistSourceTypeGroup = {
  source_type: string;
  values: ArchivistRecord[];
  uncertain: ArchivistRecord[];
  /** Document ids, not records: a document that said nothing has no value to carry. */
  silent: string[];
};

export type ArchivistAttributeGroup = {
  attribute: string;
  quantity: string;
  tag_vocabulary: string[];
  groups: ArchivistSourceTypeGroup[];
};

export type ArchivistCorpus = {
  /** Empty with zero documents is a real state: nothing has been indexed yet. */
  built_at: string;
  documents: ArchivistDocument[];
  columns: ArchivistColumn[];
  intervention_class: string;
  intervention_classes: string[];
  /** What the corpus holds, not what the vocabulary declares. */
  indications: string[];
  source_types: string[];
  orgs: string[];
};

export type ArchivistTagFilter = { attribute: string; values: string[] };

export type ArchivistQuery = {
  intervention_class: string;
  attributes?: string[];
  indications?: string[];
  source_types?: string[];
  orgs?: string[];
  tags?: ArchivistTagFilter[];
};

export type ArchivistAnswer = {
  intervention_class: string;
  built_at: string;
  documents: ArchivistDocument[];
  attributes: ArchivistAttributeGroup[];
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
  relation: "contradicts" | "extends" | "confirms" | "unrelated";
  reason: string;
  doc_block_ids?: string[];
};

export type EvidenceStrength =
  | "well_grounded"
  | "partial"
  | "thin"
  | "unsupported"
  | "unknown";

export type EvidenceAssessment = {
  attribute_ref: string;
  strength: EvidenceStrength;
  reason: string;
  doc_target: string;
  doc_block_ids: string[];
  supporting_insight_ids: string[];
  supporting_findings: Finding[];
};

export type FunnelStats = {
  queries: number;
  findings: number;
  unique_findings: number;
  insights: number;
  matches: number;
  assessments: number;
  /**
   * Announcements read for a program name, and how many named one.
   *
   * A pair, because the second alone is unreadable: an announcement naming no program
   * leaves no row in the landscape, so without the attempts a weak reading and a quiet
   * week look identical. Optional so a result saved before this existed still loads.
   */
  announcements_read?: number;
  announcements_named?: number;
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
  source_record_id: string;
  source_identity_status: "canonical" | "title_fallback" | "url_fallback";
  evidence_unit_id: string;
  evidence_unit: EvidenceUnitIdentity;
  semantic_assessment: MeasurementSemanticAssessment;
  semantic_status: "comparable" | "contextual" | "incompatible" | "unknown";
  semantic_reason: string;
  evidence_mode: "prose" | "structured_fact";
  ai_recommendation: "admit" | "reject" | "flag";
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
  failure_code: string;
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
  target_meeting_rate: number;
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
  | "unknown";

export type PrecedentSignal = {
  attribute_ref: string;
  precedent: PrecedentLabel;
  outcome: "favorable" | "mixed" | "unfavorable" | "unknown";
  reason: string;
  doc_block_ids: string[];
  coverage_insight_ids: string[];
  outcome_insight_ids: string[];
  supporting_insight_ids: string[];
  supporting_findings: Finding[];
};

export type DevelopmentProgram = {
  projection_id: string;
  name: string;
  source_role: SourceRole;
  target_relationship: TargetRelationship;
  target_relationship_reason: string;
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
  attribute_refs: string[];
  supporting_findings: Finding[];
};

/** One place's reading of one indicator, exactly as the provider stated it. */
export type IndicatorReading = {
  place: string;
  spatial_type: string;
  year: number;
  value: number | null;
  value_text: string;
  parent_place: string;
};

/**
 * One health indicator and every reading retrieved for it.
 *
 * Deliberately unsummarised: no total across countries and no single headline number. A
 * total over whichever countries happened to be retrieved would read as a total for the
 * disease.
 */
export type BurdenIndicator = {
  projection_id: string;
  indicator_code: string;
  indicator_name: string;
  readings: IndicatorReading[];
  attribute_refs: string[];
  supporting_findings: Finding[];
};

export type Variable = {
  name: string;
  description: string;
  block_ids?: string[];
  document_target: string;
  document_spans: Array<{ quote: string; block_ids: string[] }>;
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
  semantic_provenance: Record<keyof QuantitativeSemanticProfile, Array<{
    quote: string;
    block_ids: string[];
  }>>;
  provenance_spans: Array<{ quote: string; block_ids: string[] }>;
  ai_recommendation: "confirm" | "exclude" | "flag";
  ai_review_reason: string;
  review_status: "needs_review" | "approved" | "rejected";
};

export type QuantitativeStatementDisposition = {
  quote: string;
  block_ids: string[];
  disposition: "context_only" | "non_scalar" | "range_or_set" | "uncertain";
  reason: string;
  attribute_refs: string[];
};

export type QuantitativeLedgerReview = {
  unit_id: string;
  block_id: string;
  quote: string;
  classification: "target" | "partial_target" | "context_only" | "non_scalar" | "range_or_set" | "non_numeric" | "uncertain";
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

export type NumericExpression = {
  kind: "point_estimate" | "range" | "bound" | "confidence_interval" | "count" | "rate" | "other" | "unknown";
  unit: string;
  value: number | null;
  lower: number | null;
  upper: number | null;
  comparator: "" | "=" | ">" | ">=" | "<" | "<=";
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
    status: "match" | "mismatch" | "uncertain" | "not_checked";
    configured_indication: string;
    document_indication: string;
    reason: string;
    doc_block_ids: string[];
  };
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
  burden_indicators?: BurdenIndicator[];
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
 * Two citation lists that are not interchangeable: `reference_block_ids` is where the
 * bar is stated, `comparison_block_ids` is what was read to judge it. The service
 * contract checks each against its own document, so resolving either one lands a reader
 * in the file that actually says it.
 */
export type AlignmentFinding = {
  requirement_id: string;
  edge_id: string;
  requirement: string;
  reference_block_ids: string[];
  verdict: AlignmentVerdict;
  statement: string;
  /** What the measured document would have to close. Only on the two verdicts that
   * have a gap — `falls_short` and `not_comparable`. */
  gap: string;
  comparison_block_ids: string[];
};

/** One comparison Aligner declares, by document type, before any run. */
export type AlignmentEdgeSpec = {
  reference: string;
  comparison: string;
  question: string;
};

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

// --- Priority digest ---------------------------------------------------------

/**
 * One thing the tool's selector left out, and where to look at it.
 *
 * Never a repeat of a listed priority — the service drops those — and never unsourced:
 * a nomination the reader cannot open is dropped rather than shown.
 */
export type PriorityNomination = {
  label: string;
  statement: string;
  cited_block_ids: string[];
};

/**
 * A short passage about a tool's priorities, and what they miss.
 *
 * Derived on read and held for the session only. It describes a list the browser computes
 * when a result is opened, so it is never part of a result and never exported.
 */
export type PriorityDigest = {
  digest: string;
  nominations: PriorityNomination[];
};

export type PriorityDigestRequest = {
  authority: string;
  order_note: string;
  items: Array<{
    id: string;
    label: string;
    qualifier: string;
    statement: string;
    recommendation: string;
  }>;
  analysis: unknown;
  block_ids: string[];
  org: string;
  intervention_class: string;
  indication: string;
};

export async function fetchPriorityDigest(
  request: PriorityDigestRequest,
): Promise<PriorityDigest> {
  return jsonRequest<PriorityDigest>("/api/assistant/priority-digest", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
}

// --- Expert ------------------------------------------------------------------

/** One declared stage gate, for a selector that has not chosen one yet. */
export type GateSpec = {
  id: string;
  label: string;
  ordinal: number;
};

/**
 * What became of one gate question. Three values, each traceable.
 *
 * `not_applicable` means the question's own text states a class this run is not, so
 * no model read it and it is not a shortfall. `answered` and `not_found` are what a
 * model concluded from the material supplied.
 *
 * `not_found` rather than `absent`: the claim has to hold whether or not the bank's
 * "not found in what was supplied" is what the run establishes, whatever anyone expected
 * the documents to hold.
 * There were five states; two of them rested on a judgment about which document
 * could answer a question, which the source question bank does not contain.
 */
export type QuestionState =
  | "not_applicable"
  | "answered"
  | "partly_answered"
  | "not_found";

/**
 * Where an answer came from.
 *
 * `document` carries `cited_block_ids` and can be checked. `context` names a
 * transient item the user pasted for that run, whose text is deliberately not
 * retained anywhere — so the label is the entire record, and an answer sourced
 * that way can never be verified from the saved file. There is no third value, so
 * nothing can look cited without being so.
 */
export type AnswerSource = "document" | "context";

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
  source: AnswerSource | null;
  cited_block_ids: string[];
  context_label: string;
};

export type DisciplineReview = {
  id: string;
  label: string;
  questions: QuestionAssessment[];
};

export type ReviewDocument = {
  doc_id: string;
  source_type: string;
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
  /** Labels of the transient context items supplied, never their text. */
  context_labels: string[];
  org: string;
  intervention_class: string;
  indication: string;
  blocks: ContentBlock[];
};

export type ExpertResponse = { review: GateReview };

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

export const API_BASE =
  configuredApiUrl ||
  (configuredApiHost ? `https://${configuredApiHost}` : "http://localhost:8000");

async function jsonRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, init);
  if (!res.ok) {
    throw new Error((await res.text()) || `Request failed: ${res.status}`);
  }
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
  const res = await fetch(`${API_BASE}${path}`, { method: "POST", body, headers });
  if (!res.ok || !res.body) {
    throw new Error((await res.text()) || `Request failed: ${res.status}`);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let result: T | null = null;
  let error: string | null = null;

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let nl: number;
    while ((nl = buffer.indexOf("\n")) !== -1) {
      const line = buffer.slice(0, nl).trim();
      buffer = buffer.slice(nl + 1);
      if (!line) continue;
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
  }

  if (error) throw new Error(error);
  if (result === null) throw new Error("Stream ended without complete event");
  return result;
}

export async function fetchDocumentTypes(): Promise<DocumentType[]> {
  const res = await jsonRequest<{ document_types: DocumentType[] }>(
    "/api/configs/document-types",
  );
  return res.document_types;
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
): Promise<InspectorResponse> {
  const form = new FormData();
  form.append("file", file);
  appendHeader(form, header);
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

/**
 * What the archive holds. Omit the class and the server picks it.
 *
 * Optional rather than required so the client keeps no default of its own: the response
 * carries `intervention_class`, so the first call can ask for whatever is declared and
 * read back which one it got. A hardcoded "vaccine" here would be a second default, free
 * to disagree with the route's the day another class is indexed.
 */
export async function fetchArchivistCorpus(
  interventionClass?: string,
): Promise<ArchivistCorpus> {
  const query = interventionClass
    ? `?intervention_class=${encodeURIComponent(interventionClass)}`
    : "";
  return jsonRequest<ArchivistCorpus>(`/api/archivist/corpus${query}`);
}

/**
 * Read the corpus. A POST because the query is a set of filters rather than a path, and
 * nothing about it is a mutation - there is no run to start and no progress to stream,
 * which is what tells this tool apart from every other one here.
 */
export async function queryArchivist(query: ArchivistQuery): Promise<ArchivistAnswer> {
  return jsonRequest<ArchivistAnswer>("/api/archivist/query", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(query),
  });
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
 * The gates Expert can review for this org and intervention.
 *
 * Filtered by intervention on the service side, because a bank is written for the
 * modalities it names — the current ones derive from a drug milestone dictionary and ask
 * about synthetic routes and salt forms. So a modality no bank covers offers no gate,
 * which is the honest thing to show at the point of choosing.
 */
export async function fetchExpertGates(
  org: string,
  interventionClass: string,
): Promise<GateSpec[]> {
  const data = await jsonRequest<{ gates: GateSpec[] }>(
    `/api/expert/gates?org=${encodeURIComponent(org)}`
      + `&intervention=${encodeURIComponent(interventionClass)}`,
  );
  return data.gates;
}

/**
 * `contextItems` are transient: their text is sent with this one request and never
 * stored. Only the labels come back on the result, which is what lets an answer
 * name its source without the tool taking the content into its contract.
 */
export async function runExpert(
  documents: { file: File; sourceType: string }[],
  configuration: {
    gate: string;
    org: string;
    intervention_class: string;
    indication: string;
  },
  /**
   * Transient context: one attachment per item, with the name an answer is attributed
   * to. The service reads each file into text; nothing here parses one, so a format it
   * accepts is added in one place rather than two.
   */
  contextItems: { label: string; file: File }[],
  onStage?: (stage: string, progress?: StageProgress) => void,
): Promise<ExpertResponse> {
  const form = new FormData();
  documents.forEach(({ file, sourceType }) => {
    form.append("files", file);
    form.append("source_types", sourceType);
  });
  Object.entries(configuration).forEach(([key, value]) => form.append(key, value));
  contextItems.forEach(({ label, file }) => {
    form.append("context_labels", label);
    form.append("context_files", file);
  });
  return streamRequest("/api/expert/run", form, onStage);
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
