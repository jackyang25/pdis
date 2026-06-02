export type Header = {
  org: string;
  source_type: string;
  intervention_class: string;
  indication: string;
};

export type ToolName = "chunker" | "benchmarker" | "reviewer";

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
};

export type Claim = {
  id: string;
  ordinal: number;
  statement: string;
  claim_type: string;
  polarity: string;
  source_id: string;
  source_kind: string;
  source_locator: Record<string, unknown>;
  attribute_ref: string | null;
  org: string | null;
  source_type: string | null;
  intervention_class: string | null;
  indication: string | null;
};

export type DimensionName = "completeness" | "adherence" | "expertise";

export type DimensionGrade = {
  grade: string;
  issues: string[];
  recommendation: string;
  cited_claim_ids: string[];
};

export type Dimensions = Record<DimensionName, DimensionGrade>;

export type VariableGrade = {
  variable_name: string;
  dimensions: Dimensions;
  block_ids: string[];
  attribute_ref: string | null;
};

export type SectionGrade = {
  section_name: string;
  is_present: boolean;
  dimensions: Dimensions;
  missing_variables: string[];
  variable_grades: VariableGrade[];
};

export type ReviewResult = {
  doc_id: string;
  dimensions: Dimensions;
  top_issues: string[];
  section_grades: SectionGrade[];
  org: string | null;
  source_type: string | null;
  intervention_class: string | null;
  indication: string | null;
};

export const DIMENSION_NAMES: DimensionName[] = ["completeness", "adherence", "expertise"];

export const GRADE_LABELS: Record<string, string> = {
  A: "Fully complete",
  B: "Substantially complete",
  C: "Partially complete",
  D: "Significant gaps",
  F: "Incomplete",
  "N/A": "Not applicable",
};

export type PeerClaim = {
  source_id: string;
  statement: string;
  claim_type: string | null;
  attribute_ref: string | null;
  valid_as_of: string | null;
  extracted_at: string | null;
  org: string | null;
  source_type: string | null;
  indication: string | null;
};

export type ReviewerResponse = {
  review: ReviewResult;
  peer_claims: PeerClaim[];
};

export type Finding = {
  url: string;
  title: string;
  query: string;
  retrieved_at: string;
  excerpt: string | null;
  published_at: string | null;
};

export type SearcherResponse = {
  query: string;
  findings: Finding[];
};

export type Insight = {
  statement: string;
  query: string;
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
};

export type MonitorResponse = {
  org: string;
  source_type: string;
  intervention_class: string;
  indication: string;
  matches: Match[];
};

export type StageEvent = { event: "stage"; name: string };
export type CompleteEvent<T> = { event: "complete"; result: T };
export type ErrorEvent = { event: "error"; detail: string };
export type StreamEvent<T> = StageEvent | CompleteEvent<T> | ErrorEvent;

const API_BASE = process.env.NEXT_PUBLIC_PDIS_API_URL || "http://localhost:8000";

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
  body: FormData,
  onStage?: (stage: string) => void,
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { method: "POST", body });
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
        onStage?.(event.name);
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

export async function runBenchmarker(
  file: File,
  header: Header,
  onStage?: (stage: string) => void,
): Promise<{ doc_id: string; source_id: string; claims: Claim[] }> {
  const form = new FormData();
  form.append("file", file);
  appendHeader(form, header);
  return streamRequest("/api/benchmarker/run", form, onStage);
}

export async function runReviewer(
  file: File,
  header: Header,
  onStage?: (stage: string) => void,
): Promise<ReviewerResponse> {
  const form = new FormData();
  form.append("file", file);
  appendHeader(form, header);
  return streamRequest("/api/reviewer/run", form, onStage);
}

export async function runSearcher(
  query: string,
  onStage?: (stage: string) => void,
): Promise<SearcherResponse> {
  const form = new FormData();
  form.append("query", query);
  return streamRequest("/api/searcher/run", form, onStage);
}

export async function runMonitor(
  files: File[],
  header: Header,
  onStage?: (stage: string) => void,
): Promise<MonitorResponse> {
  const form = new FormData();
  for (const file of files) {
    form.append("files", file);
  }
  appendHeader(form, header);
  return streamRequest("/api/monitor/run", form, onStage);
}
