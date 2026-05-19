export type Header = {
  org: string;
  source_type: string;
  intervention_class: string;
  therapeutic_area: string | null;
};

export type TriplesResponse = {
  orgs: string[];
  source_types_by_org: Record<string, string[]>;
  interventions_by_org_source: Record<string, string[]>;
};

export type ContentBlock = {
  id: string;
  doc_id: string;
  ordinal: number;
  block_type: string;
  content: string;
  heading_stack: string[];
  section_label: string | null;
  label_confidence: string | null;
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
  binding_confidence: string | null;
  evidence_strength: string | null;
  recency_tier: string | null;
  org: string | null;
  source_type: string | null;
  intervention_class: string | null;
  therapeutic_area: string | null;
};

export type VariableGrade = {
  variable_name: string;
  grade: string;
  issues: string[];
  recommendation: string;
  block_ids: string[];
};

export type SectionGrade = {
  section_name: string;
  grade: string;
  is_present: boolean;
  missing_variables: string[];
  issues: string[];
  recommendation: string;
  variable_grades: VariableGrade[];
};

export type ReviewResult = {
  doc_id: string;
  overall_grade: string;
  top_issues: string[];
  section_grades: SectionGrade[];
  org: string | null;
  source_type: string | null;
  intervention_class: string | null;
  therapeutic_area: string | null;
};

export type PeerClaim = {
  source_id: string;
  statement: string;
  attribute_ref: string | null;
  binding_confidence: string | null;
  evidence_strength: string | null;
};

export type PDReviewerResponse = {
  review: ReviewResult;
  peer_claims: PeerClaim[];
};

const API_BASE = process.env.NEXT_PUBLIC_PDIS_API_URL || "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, init);
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(detail || `Request failed: ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export async function fetchTriples(): Promise<TriplesResponse> {
  return request<TriplesResponse>("/api/configs/triples");
}

export async function fetchTherapeuticAreas(intervention: string): Promise<string[]> {
  const res = await request<{ therapeutic_areas: string[] }>(
    `/api/configs/therapeutic-areas?intervention=${encodeURIComponent(intervention)}`,
  );
  return res.therapeutic_areas;
}

function appendHeader(form: FormData, header: Header) {
  form.append("org", header.org);
  form.append("source_type", header.source_type);
  form.append("intervention_class", header.intervention_class);
  if (header.therapeutic_area) {
    form.append("therapeutic_area", header.therapeutic_area);
  }
}

export async function runChunker(
  file: File,
  header: Header,
  options: { label: boolean },
): Promise<{ doc_id: string; blocks: ContentBlock[] }> {
  const form = new FormData();
  form.append("file", file);
  appendHeader(form, header);
  form.append("label", String(options.label));
  return request("/api/chunker/run", { method: "POST", body: form });
}

export async function runEvidence(
  file: File,
  header: Header,
): Promise<{ doc_id: string; source_id: string; claims: Claim[] }> {
  const form = new FormData();
  form.append("file", file);
  appendHeader(form, header);
  return request("/api/evidence/run", { method: "POST", body: form });
}

export async function runPDReviewer(
  file: File,
  header: Header,
  options: { usePeerClaims: boolean },
): Promise<PDReviewerResponse> {
  const form = new FormData();
  form.append("file", file);
  appendHeader(form, header);
  form.append("use_peer_claims", String(options.usePeerClaims));
  return request("/api/pd-reviewer/run", { method: "POST", body: form });
}
