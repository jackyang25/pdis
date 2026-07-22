import type { AlignerResponse, ContentBlock, InspectorResponse, ScoutResponse } from "./api";

const RESULT_SCHEMA = "pdis.result" as const;
const RESULT_VERSION = 13 as const;
type ResultVersion = 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | typeof RESULT_VERSION;

type ResultType = "aligner" | "inspector" | "scout";
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
type AlignerAnalysis = {
  alignment: Omit<AlignerResponse["alignment"], "blocks">;
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

export function packAlignerResult(
  result: AlignerResponse,
): ResultFile<"aligner", AlignerAnalysis> {
  const { blocks, ...alignment } = result.alignment;
  return {
    schema: RESULT_SCHEMA,
    version: RESULT_VERSION,
    result_type: "aligner",
    analysis: { alignment },
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

export function unpackAlignerResult(value: unknown): AlignerResponse {
  if (isResultFile(value)) {
    assertResultType(value, "aligner");
    const analysis = value.analysis as AlignerAnalysis;
    if (!analysis.alignment) throw new Error("not an Aligner result file");
    return {
      alignment: {
        ...analysis.alignment,
        blocks: flattenDocuments(value.source_documents),
      },
    };
  }
  const raw = value as Partial<AlignerResponse>;
  if (!raw.alignment || !Array.isArray(raw.alignment.links)) {
    throw new Error("not an Aligner result file");
  }
  return {
    alignment: {
      ...raw.alignment,
      blocks: Array.isArray(raw.alignment.blocks) ? raw.alignment.blocks : [],
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
    ([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, RESULT_VERSION] as const).includes(
      candidate.version as ResultVersion,
    ) &&
    (candidate.result_type === "aligner" ||
      candidate.result_type === "inspector" ||
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
    conformity: (raw.conformity ?? []).map(normalizeConformity),
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

function normalizeConformity(score: Record<string, any>): Record<string, unknown> {
  const {
    conformity: _legacyConformity,
    lower: _legacyLower,
    upper: _legacyUpper,
    weighted_target_meeting_rate: _legacyWeightedRate,
    ...currentScore
  } = score;
  const measurements: Record<string, any>[] = (score.measurements ?? []).map(
    (measurement: Record<string, any>) => normalizeMeasurement(measurement, score.unit),
  );
  const values = measurements
    .map((measurement: Record<string, unknown>) => Number(measurement.value))
    .filter(Number.isFinite)
    .sort((left: number, right: number) => left - right);
  const target = Number(score.target_value);
  const rawPercentile = values.length > 0 && Number.isFinite(target)
    ? empiricalPercentile(values, target)
    : null;
  const ambitionPercentile = rawPercentile == null
    ? null
    : score.comparator === "<=" ? 1 - rawPercentile : rawPercentile;
  const count = values.length;
  const targetMeetingCount = values.filter((value) =>
    score.comparator === "<=" ? value <= target : value >= target
  ).length;
  const targetMeetingRate = count > 0 ? targetMeetingCount / count : 0;
  const legacyUnverified = !score.target_quote || measurements.some(
    (measurement) => !measurement.source_quote || !Object.keys(measurement.comparability ?? {}).length,
  );

  return {
    ...currentScore,
    target_quote: score.target_quote ?? "",
    target_meeting_count: score.target_meeting_count ?? targetMeetingCount,
    target_meeting_rate: score.target_meeting_rate ?? targetMeetingRate,
    benchmark_count: score.benchmark_count ?? count,
    benchmark_minimum: score.benchmark_minimum ?? (count ? values[0] : null),
    benchmark_maximum: score.benchmark_maximum ?? (count ? values[count - 1] : null),
    benchmark_mean:
      score.benchmark_mean ?? (count ? values.reduce((sum, value) => sum + value, 0) / count : null),
    benchmark_median: score.benchmark_median ?? quantile(values, 0.5),
    benchmark_lower_quartile:
      score.benchmark_lower_quartile ?? quantile(values, 0.25),
    benchmark_upper_quartile:
      score.benchmark_upper_quartile ?? quantile(values, 0.75),
    benchmark_standard_deviation:
      score.benchmark_standard_deviation ?? sampleStandardDeviation(values),
    target_percentile: score.target_percentile ?? rawPercentile,
    ambition_percentile: score.ambition_percentile ?? ambitionPercentile,
    calibration_status: legacyUnverified
      ? "legacy_unverified"
      : score.calibration_status ?? (count >= 5 ? "sufficient" : count >= 2 ? "limited" : "insufficient"),
    doc_block_ids: score.doc_block_ids ?? [],
    measurements,
    excluded_measurements: (score.excluded_measurements ?? []).map(
      (measurement: Record<string, any>) => normalizeMeasurement(measurement, score.unit),
    ),
  };
}

function sampleStandardDeviation(values: number[]): number | null {
  if (values.length < 2) return null;
  const mean = values.reduce((sum, value) => sum + value, 0) / values.length;
  const variance = values.reduce((sum, value) => sum + (value - mean) ** 2, 0)
    / (values.length - 1);
  return Math.sqrt(variance);
}

function quantile(values: number[], probability: number): number | null {
  if (values.length === 0) return null;
  const position = (values.length - 1) * probability;
  const lower = Math.floor(position);
  const upper = Math.ceil(position);
  if (lower === upper) return values[lower];
  return values[lower] + (position - lower) * (values[upper] - values[lower]);
}

function empiricalPercentile(values: number[], target: number): number {
  const below = values.filter((value) => value < target).length;
  const equal = values.filter((value) => value === target).length;
  return (below + 0.5 * equal) / values.length;
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
    weight: _legacyWeight,
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
    source_quote: current.source_quote ?? "",
    source_record_id: current.source_record_id ?? "",
    source_identity_status: current.source_identity_status ?? "url_fallback",
    comparability: current.comparability ?? {},
    comparability_reasons: current.comparability_reasons ?? {},
    inclusion_reason: current.inclusion_reason ?? "",
    exclusion_reasons: current.exclusion_reasons ?? [],
    age_months: current.age_months ?? null,
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
