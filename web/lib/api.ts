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

export type DimensionName = "completeness" | "adherence" | "rigor";
export type Grade = "A" | "B" | "C" | "D" | "F" | "N/A";

export type DimensionGrade = {
  grade: Grade;
  issues: string[];
  recommendation: string;
};

export type Dimensions = Record<DimensionName, DimensionGrade>;

export type VariableGrade = {
  variable_name: string;
  dimensions: Dimensions;
  block_ids: string[];
};

export type SectionGrade = {
  section_name: string;
  is_present: boolean;
  dimensions: Dimensions;
  missing_variables: string[];
  variable_grades: VariableGrade[];
};

export type CrossSectionFinding = {
  description: string;
  sections: string[];
  recommendation: string;
  block_ids: string[];
};

export type InspectionResult = {
  doc_id: string;
  dimensions: Dimensions;
  top_issues: string[];
  section_grades: SectionGrade[];
  cross_section_findings: CrossSectionFinding[];
  consistency_status: "complete" | "partial" | "failed" | "not_applicable" | "unknown";
  grading_status: "complete" | "unknown";
  org: string | null;
  source_type: string | null;
  intervention_class: string | null;
  indication: string | null;
  // The parsed source document behind the grades (for the Ask assistant).
  blocks: ContentBlock[];
};

export const DIMENSION_NAMES: DimensionName[] = ["completeness", "adherence", "rigor"];

export const GRADE_LABELS: Record<string, string> = {
  A: "Fully meets expectations",
  B: "Substantially meets expectations",
  C: "Partially meets expectations",
  D: "Significant gaps",
  F: "Does not meet expectations",
  "N/A": "Not applicable",
};

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
  safety_records?: SafetyRecord[];
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
};

export type SafetyRecord = {
  product_name: string;
  signal_type: "label_warning" | "reported_event" | "device_event" | "recall";
  signal: string;
  detail: string;
  count: number | null;
  qualification: string;
};

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
  status: "measurements_found" | "no_relevant_measurement" | "uncertain";
  reason: string;
  url: string;
  insight_id: string;
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
  calibration_status: "insufficient" | "limited" | "sufficient" | "legacy_unverified";
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
  name: string;
  sponsors: string[];
  phases: string[];
  statuses: string[];
  record_types: string[];
  record_ids: string[];
  attribute_refs: string[];
  supporting_findings: Finding[];
};

export type SafetySignal = {
  product_name: string;
  signal_type: "label_warning" | "reported_event" | "device_event" | "recall";
  signal: string;
  detail: string;
  count: number | null;
  qualification: string;
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
  safety_signals: SafetySignal[];
  stats: FunnelStats;
  // The parsed source document behind the analysis (for the Ask assistant).
  blocks: ContentBlock[];
};

export type AlignmentUnitType =
  | "target"
  | "activity"
  | "milestone"
  | "requirement"
  | "dependency"
  | "risk_response";

export type AlignmentRelation =
  | "aligned"
  | "modified"
  | "conflict"
  | "missing"
  | "introduced";

export type AlignmentLabel = { name: string; description: string };

export type AlignmentDocument = {
  role: "reference" | "comparison";
  doc_id: string;
  source_type: string;
  display_name: string;
};

export type AlignmentUnit = {
  id: string;
  document_role: "reference" | "comparison";
  document_id: string;
  unit_type: AlignmentUnitType;
  statement: string;
  block_ids: string[];
};

export type AlignmentLink = {
  id: string;
  relation: AlignmentRelation;
  reference_unit_ids: string[];
  comparison_unit_ids: string[];
  reason: string;
  reference_block_ids: string[];
  comparison_block_ids: string[];
};

export type AlignmentResult = {
  reference_document: AlignmentDocument;
  comparison_document: AlignmentDocument;
  units: AlignmentUnit[];
  links: AlignmentLink[];
  stats: Record<AlignmentRelation, number> & {
    reference_units: number;
    comparison_units: number;
  };
  org: string;
  intervention_class: string;
  indication: string;
  unit_types: AlignmentLabel[];
  relations: AlignmentLabel[];
  blocks: ContentBlock[];
};

export type AlignerResponse = { alignment: AlignmentResult };

export type StageProgress = { completed: number; total: number };
export type StageEvent = { event: "stage"; name: string; completed?: number; total?: number };
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

export async function runAligner(
  referenceFile: File,
  comparisonFile: File,
  configuration: {
    org: string;
    reference_source_type: string;
    comparison_source_type: string;
    intervention_class: string;
    indication: string;
  },
  onStage?: (stage: string, progress?: StageProgress) => void,
): Promise<AlignerResponse> {
  const form = new FormData();
  form.append("reference_file", referenceFile);
  form.append("comparison_file", comparisonFile);
  Object.entries(configuration).forEach(([key, value]) => form.append(key, value));
  return streamRequest("/api/aligner/run", form, onStage);
}

// --- Ask: read-only, grounded chat over any result object ---
export type AskMessage = { role: "user" | "assistant"; content: string };

export async function askAssistant(
  resultType: string,
  result: unknown,
  messages: AskMessage[],
  document?: ContentBlock[],
): Promise<string> {
  const res = await jsonRequest<{ answer: string }>("/api/assistant/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ result_type: resultType, result, messages, document }),
  });
  return res.answer;
}
