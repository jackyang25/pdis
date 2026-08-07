export type Header = {
  org: string;
  source_type: string;
  intervention_class: string;
  indication: string;
};

export type ToolName = "chunker" | "aligner" | "inspector" | "scout";

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

export const LEVEL_LABELS: Record<FindingLevel, string> = {
  not_met: "Not met",
  could_be_stronger: "Could be stronger",
};

export const STATUS_LABELS: Record<UnitStatus, string> = {
  met: "Meets the rubric",
  could_be_stronger: "Supplied and usable, but could be stronger",
  not_met: "The rubric asks for this and the document does not usably supply it",
  not_applicable: "The rubric accepts this being absent",
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

export type SearcherResponse = {
  query: string;
  findings: Finding[];
};

export type SearchSource = {
  key: string;
  label: string;
  default_enabled: boolean;
  configured: boolean;
  evidence_domains: string[];
  required_entity_types: string[];
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
  reference_doc_id: string;
  comparison_doc_id: string;
  question: string;
};

/** One comparison Aligner declares, by document type, before any run. */
export type AlignmentEdgeSpec = {
  reference: string;
  comparison: string;
  question: string;
};

/**
 * Identified documents, the comparisons they resolve, and their parsed source.
 *
 * Carries no findings. Aligner's extract-and-link stages were removed because
 * their relation vocabulary was symmetric - it described how two documents
 * differed, never whether the second met the bar the first set - and the shape
 * that replaces it is not yet decided. Findings arrive as fields beside these,
 * citing `blocks` for lineage the way every other tool does.
 */
export type AlignmentResult = {
  documents: AlignmentDocument[];
  edges: AlignmentEdge[];
  org: string;
  intervention_class: string;
  indication: string;
  blocks: ContentBlock[];
};

export type AlignerResponse = { alignment: AlignmentResult };

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
  onStage?: (stage: string) => void,
): Promise<SearcherResponse> {
  const form = new FormData();
  form.append("query", query);
  form.append("sources", sources.join(","));
  return streamRequest("/api/searcher/run", form, onStage);
}

export async function fetchSearchSources(): Promise<SearchSource[]> {
  return jsonRequest<SearchSource[]>("/api/searcher/sources");
}

export async function runScout(
  files: File[],
  header: Header,
  onStage?: (stage: string, progress?: StageProgress) => void,
): Promise<ScoutResponse> {
  const form = new FormData();
  for (const file of files) {
    form.append("files", file);
  }
  appendHeader(form, header);
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
