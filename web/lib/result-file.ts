import type { ContentBlock, InspectorResponse, ScoutResponse } from "./api";

const RESULT_SCHEMA = "pdis.result" as const;
const RESULT_VERSION = 10 as const;
type ResultVersion = 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | typeof RESULT_VERSION;

type ResultType = "inspector" | "scout";
type StoredResultType = ResultType | "reviewer";

type SourceDocument = {
  doc_id: string;
  blocks: ContentBlock[];
};

type ResultFile<TResultType extends StoredResultType, TAnalysis> = {
  schema: typeof RESULT_SCHEMA;
  version: ResultVersion;
  result_type: TResultType;
  analysis: TAnalysis;
  source_documents: SourceDocument[];
};

type ScoutAnalysis = Omit<ScoutResponse, "blocks">;
type InspectorAnalysis = {
  inspection: Omit<InspectorResponse["inspection"], "blocks">;
};
type LegacyReviewerAnalysis = {
  review: Omit<InspectorResponse["inspection"], "blocks">;
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

export function packInspectorResult(
  result: InspectorResponse,
): ResultFile<"inspector", InspectorAnalysis> {
  const { blocks, ...inspection } = result.inspection;
  return {
    schema: RESULT_SCHEMA,
    version: RESULT_VERSION,
    result_type: "inspector",
    analysis: { inspection },
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

export function unpackInspectorResult(value: unknown): InspectorResponse {
  if (isResultFile(value)) {
    const blocks = flattenDocuments(value.source_documents);
    if (value.result_type === "inspector") {
      const analysis = value.analysis as InspectorAnalysis;
      return {
        inspection: {
          ...analysis.inspection,
          blocks,
        },
      };
    }
    // Import-only migration for saved files produced before Reviewer was
    // renamed to Inspector. Runtime components never consume this old shape.
    if (value.result_type === "reviewer") {
      const analysis = value.analysis as LegacyReviewerAnalysis;
      return {
        inspection: {
          ...analysis.review,
          blocks,
        },
      };
    }
    throw new Error(`expected an inspector result, received ${value.result_type}`);
  }
  const raw = value as Partial<InspectorResponse> & {
    review?: InspectorResponse["inspection"];
  };
  const inspection = raw.inspection ?? raw.review;
  if (!inspection) {
    throw new Error("not an Inspector result file");
  }
  return {
    inspection: {
      ...inspection,
      blocks: Array.isArray(inspection.blocks) ? inspection.blocks : [],
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

function isResultFile(value: unknown): value is ResultFile<StoredResultType, unknown> {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<ResultFile<StoredResultType, unknown>>;
  return (
    candidate.schema === RESULT_SCHEMA &&
    ([1, 2, 3, 4, 5, 6, 7, 8, 9, RESULT_VERSION] as const).includes(
      candidate.version as ResultVersion,
    ) &&
    (candidate.result_type === "inspector" ||
      candidate.result_type === "reviewer" ||
      candidate.result_type === "scout") &&
    candidate.analysis != null &&
    Array.isArray(candidate.source_documents)
  );
}

function assertResultType(
  result: ResultFile<StoredResultType, unknown>,
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
    context_validation: raw.context_validation ?? {
      status: "not_checked",
      configured_indication: String(raw.indication ?? ""),
      document_indication: "",
      reason: "This imported result predates document-context validation.",
      doc_block_ids: [],
    },
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
    development_landscape: (raw.development_landscape ?? []).map(
      (program: Record<string, any>) => ({
        ...program,
        sponsors: program.sponsors ?? [],
        phases: program.phases ?? [],
        statuses: program.statuses ?? [],
        record_types: program.record_types ?? [],
        record_ids: program.record_ids ?? [],
        attribute_refs: program.attribute_refs ?? [],
        supporting_findings: program.supporting_findings ?? [],
      }),
    ),
    safety_signals: (raw.safety_signals ?? []).map(
      (signal: Record<string, any>) => ({
        ...signal,
        detail: signal.detail ?? "",
        count: signal.count ?? null,
        qualification: signal.qualification ?? "",
        attribute_refs: signal.attribute_refs ?? [],
        supporting_findings: signal.supporting_findings ?? [],
      }),
    ),
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
