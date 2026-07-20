import type { ContentBlock, ReviewerResponse, ScoutResponse } from "./api";

const RESULT_SCHEMA = "pdis.result" as const;
const RESULT_VERSION = 7 as const;
type ResultVersion = 1 | 2 | 3 | 4 | 5 | 6 | typeof RESULT_VERSION;

type ResultType = "reviewer" | "scout";

type SourceDocument = {
  doc_id: string;
  blocks: ContentBlock[];
};

type ResultFile<TResultType extends ResultType, TAnalysis> = {
  schema: typeof RESULT_SCHEMA;
  version: ResultVersion;
  result_type: TResultType;
  analysis: TAnalysis;
  source_documents: SourceDocument[];
};

type ScoutAnalysis = Omit<ScoutResponse, "blocks">;
type ReviewerAnalysis = {
  review: Omit<ReviewerResponse["review"], "blocks">;
};

/** Build a portable artifact without coupling the analysis tree to document text. */
export function packScoutResult(result: ScoutResponse): ResultFile<"scout", ScoutAnalysis> {
  const { blocks, ...analysis } = result;
  return {
    schema: RESULT_SCHEMA,
    version: RESULT_VERSION,
    result_type: "scout",
    analysis,
    source_documents: groupDocuments(blocks),
  };
}

export function packReviewerResult(
  result: ReviewerResponse,
): ResultFile<"reviewer", ReviewerAnalysis> {
  const { blocks, ...review } = result.review;
  return {
    schema: RESULT_SCHEMA,
    version: RESULT_VERSION,
    result_type: "reviewer",
    analysis: { review },
    source_documents: groupDocuments(blocks),
  };
}

/** Read the new envelope or normalize a legacy result that stored `blocks`
 * directly on its analysis object. Legacy files without blocks remain usable. */
export function unpackScoutResult(value: unknown): ScoutResponse {
  if (isResultFile(value)) {
    assertResultType(value, "scout");
    return normalizeScoutResult(
      value.analysis,
      flattenDocuments(value.source_documents),
    );
  }
  const raw = value as Partial<ScoutResponse>;
  return normalizeScoutResult(
    value,
    Array.isArray(raw?.blocks) ? raw.blocks : [],
  );
}

export function unpackReviewerResult(value: unknown): ReviewerResponse {
  if (isResultFile(value)) {
    assertResultType(value, "reviewer");
    const analysis = value.analysis as ReviewerAnalysis;
    return {
      ...analysis,
      review: {
        ...analysis.review,
        blocks: flattenDocuments(value.source_documents),
      },
    };
  }
  const legacy = value as ReviewerResponse;
  return {
    ...legacy,
    review: {
      ...legacy.review,
      blocks: Array.isArray(legacy?.review?.blocks) ? legacy.review.blocks : [],
    },
  };
}

/** Separate document context from an analysis before sending it to Ask. */
export function splitResultContext(result: unknown): {
  analysis: unknown;
  document?: ContentBlock[];
} {
  if (result && typeof result === "object" && "blocks" in result) {
    const { blocks, ...analysis } = result as Record<string, unknown> & {
      blocks?: ContentBlock[];
    };
    return {
      analysis,
      document: Array.isArray(blocks) && blocks.length > 0 ? blocks : undefined,
    };
  }
  return { analysis: result };
}

function isResultFile(value: unknown): value is ResultFile<ResultType, unknown> {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<ResultFile<ResultType, unknown>>;
  return (
    candidate.schema === RESULT_SCHEMA &&
    ([1, 2, 3, 4, 5, 6, RESULT_VERSION] as const).includes(
      candidate.version as ResultVersion,
    ) &&
    (candidate.result_type === "reviewer" || candidate.result_type === "scout") &&
    candidate.analysis != null &&
    Array.isArray(candidate.source_documents)
  );
}

function assertResultType(
  result: ResultFile<ResultType, unknown>,
  expected: ResultType,
): void {
  if (result.result_type !== expected) {
    throw new Error(`expected a ${expected} result, received ${result.result_type}`);
  }
}

function groupDocuments(blocks: ContentBlock[]): SourceDocument[] {
  const grouped = new Map<string, ContentBlock[]>();
  for (const block of blocks ?? []) {
    const docId = block.doc_id || "document";
    const existing = grouped.get(docId);
    if (existing) existing.push(block);
    else grouped.set(docId, [block]);
  }
  return Array.from(grouped, ([doc_id, documentBlocks]) => ({
    doc_id,
    blocks: documentBlocks,
  }));
}

function flattenDocuments(documents: SourceDocument[]): ContentBlock[] {
  return documents.flatMap((document) => document.blocks ?? []);
}

/** Migrate old result files once at the import boundary. Runtime components
 * consume only the current contract and contain no legacy branches. */
function normalizeScoutResult(value: unknown, blocks: ContentBlock[]): ScoutResponse {
  const raw = (value ?? {}) as Record<string, any>;
  const assessmentsByAttribute = new Map<string, Record<string, any>>(
    (raw.assessments ?? []).map((assessment: Record<string, any>) => [
      String(assessment.attribute_ref ?? ""),
      assessment,
    ]),
  );
  return {
    ...raw,
    assessments: (raw.assessments ?? []).map((assessment: Record<string, any>) => {
      const { basis: _removedBasis, ...current } = assessment;
      return {
        ...current,
        doc_target: current.doc_target ?? "",
        doc_block_ids: current.doc_block_ids ?? [],
        supporting_insight_ids: current.supporting_insight_ids ?? [],
        supporting_findings: current.supporting_findings ?? [],
      };
    }),
    conformity: (raw.conformity ?? []).map((score: Record<string, any>) => ({
      ...score,
      doc_block_ids: score.doc_block_ids ?? [],
      measurements: (score.measurements ?? []).map(
        (measurement: Record<string, any>) => normalizeMeasurement(measurement, score.unit),
      ),
    })),
    precedents: (raw.precedents ?? []).map(normalizePrecedent),
    search_plan: (raw.search_plan ?? []).map((trace: Record<string, any>) => ({
      ...trace,
      connector: trace.connector ?? "",
      operation: trace.operation ?? "",
      request_options: trace.request_options ?? {},
      tracks: trace.tracks ?? [],
      doc_block_ids: trace.doc_block_ids ?? [],
      intent_ids: trace.intent_ids ?? [],
      input_queries: trace.input_queries ?? [],
      applicability: trace.applicability ?? "applicable",
      applicability_reason: trace.applicability_reason ?? "",
      status: trace.status ?? "complete",
      error: trace.error ?? "",
      source_urls: trace.source_urls ?? [],
    })),
    variables: (raw.variables ?? []).map((variable: Record<string, any>) => {
      const assessment = assessmentsByAttribute.get(String(variable.name ?? ""));
      const documentTarget = variable.document_target ?? assessment?.doc_target ?? "";
      const blockIds = variable.block_ids?.length
        ? variable.block_ids
        : assessment?.doc_block_ids ?? [];
      const inferredMode = raw.source_type === "ipdp" ? "dynamic" : "fixed";
      const definitionMode =
        variable.definition_mode === "fixed" || variable.definition_mode === "dynamic"
          ? variable.definition_mode
          : inferredMode;
      return {
        ...variable,
        block_ids: blockIds,
        document_target: documentTarget,
        definition_mode: definitionMode,
        evidence_domain: variable.evidence_domain ?? "general",
        entities: Array.isArray(variable.entities) ? variable.entities : [],
        target_resolved:
          typeof variable.target_resolved === "boolean"
            ? variable.target_resolved
            : Boolean(documentTarget || assessment),
      };
    }),
    matches: raw.matches ?? [],
    blocks,
  } as ScoutResponse;
}

function normalizeMeasurement(
  measurement: Record<string, any>,
  targetUnit: unknown,
): Record<string, unknown> {
  const {
    study_design: studyDesign,
    publication_status: publicationStatus,
    evidence_type: evidenceType,
    source_type: sourceType,
    ...current
  } = measurement;
  const legacy = legacyMeasurementAxes(evidenceType ?? sourceType);
  return {
    ...current,
    unit: current.unit ?? (typeof targetUnit === "string" ? targetUnit : ""),
    evidence_form: current.evidence_form ?? studyDesign ?? legacy.evidenceForm,
    development_phase: current.development_phase ?? legacy.developmentPhase,
    source_record_type:
      current.source_record_type ?? publicationStatus ?? legacy.sourceRecordType,
    insight_id: current.insight_id ?? "",
  };
}

function legacyMeasurementAxes(value: unknown): {
  evidenceForm: string;
  developmentPhase: string;
  sourceRecordType: string;
} {
  const mappings: Record<string, [string, string, string]> = {
    systematic_review_meta_analysis: ["evidence_synthesis", "not_applicable", "peer_reviewed"],
    rct_phase3: ["randomized_trial", "phase_3", "peer_reviewed"],
    rct_phase2: ["randomized_trial", "phase_2", "peer_reviewed"],
    regulatory_assessment: ["regulatory_review", "not_applicable", "regulatory"],
    clinical_trial_registry: ["registry_record", "unknown", "registry"],
    observational_study: ["observational_study", "not_applicable", "peer_reviewed"],
    program_effectiveness: ["implementation_evidence", "not_applicable", "unknown"],
    preprint: ["other", "unknown", "preprint"],
    press_release: ["other", "unknown", "company_report"],
  };
  const [evidenceForm, developmentPhase, sourceRecordType] =
    mappings[String(value ?? "")] ?? ["other", "unknown", "unknown"];
  return { evidenceForm, developmentPhase, sourceRecordType };
}

function normalizePrecedent(signal: Record<string, any>): Record<string, unknown> {
  const legacy: Record<string, [string, string]> = {
    established: ["direct", "unknown"],
    emerging: ["adjacent", "unknown"],
    novel: ["none", "unknown"],
    disconfirmed: ["direct", "unfavorable"],
  };
  const [precedent, legacyOutcome] =
    legacy[String(signal.precedent)] ?? [signal.precedent ?? "unknown", "unknown"];
  return {
    ...signal,
    precedent,
    outcome: signal.outcome ?? legacyOutcome,
    doc_block_ids: signal.doc_block_ids ?? [],
    coverage_insight_ids:
      signal.coverage_insight_ids ?? signal.supporting_insight_ids ?? [],
    outcome_insight_ids: signal.outcome_insight_ids ?? [],
    supporting_insight_ids: signal.supporting_insight_ids ?? [],
    supporting_findings: signal.supporting_findings ?? [],
  };
}
