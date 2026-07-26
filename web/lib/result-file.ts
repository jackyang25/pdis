import type { AlignerResponse, ContentBlock, InspectorResponse, ScoutResponse } from "./api";

const RESULT_SCHEMA = "pdis.result" as const;
const RESULT_VERSION = 32 as const;
// Version 32 carries independent AI evidence-admission recommendations.
// Version 31 carries independent AI target-review recommendations.
// Version 30 freezes reviewed document targets before retrieval and records the
// explicit Scout phase. Only final results are exportable.
// Version 29 identifies independent evidence units within source records.
// Version 28 marks portable artifacts as finalized and prohibits unresolved
// quantitative review candidates.
const SCOUT_QUANTITATIVE_CONTRACT_SINCE_VERSION = 24 as const;
const SCOUT_CLAIM_CONTRACT_SINCE_VERSION = 26 as const;
const SCOUT_ADMISSION_CONTRACT_SINCE_VERSION = 27 as const;
const SCOUT_EVIDENCE_UNIT_CONTRACT_SINCE_VERSION = 29 as const;
type ResultVersion = 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 | 15 | 16 | 17 | 18 | 19 | 20 | 21 | 22 | 23 | 24 | 25 | 26 | 27 | 28 | 29 | 30 | 31 | typeof RESULT_VERSION;

type ResultType = "aligner" | "inspector" | "scout";
type StoredResultType = ResultType | "reviewer";

type SourceDocument = {
  doc_id: string;
  blocks: ContentBlock[];
};

type ResultFile<TResultType extends StoredResultType, TAnalysis> = {
  schema: typeof RESULT_SCHEMA;
  version: ResultVersion;
  state?: "final";
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

/** Pending admissions make a Scout analysis a review draft, not a final result. */
export function pendingQuantitativeReviewCount(result: ScoutResponse): number {
  const targetReviews = (result.quantitative_ledger?.targets ?? [])
    .filter((target) => target.review_status === "needs_review").length;
  const statementReviews = (result.quantitative_ledger?.reviews ?? [])
    .filter((review) => review.review_status === "needs_review").length;
  const evidenceReviews = (result.conformity ?? []).reduce(
    (total, score) => total + [...score.measurements, ...score.excluded_measurements]
      .filter((measurement) => measurement.admission_status === "needs_review")
      .length,
    0,
  );
  return targetReviews + statementReviews + evidenceReviews;
}

export function isScoutResultFinal(result: ScoutResponse): boolean {
  return result.phase === "final" && pendingQuantitativeReviewCount(result) === 0;
}

function hasCompleteEvidenceUnitContract(result: ScoutResponse): boolean {
  return (result.conformity ?? []).every((score) => {
    const admittedIds = score.measurements.map((measurement) => measurement.evidence_unit_id);
    return score.calibration_status !== "legacy_unverified"
      && admittedIds.every(Boolean)
      && new Set(admittedIds).size === admittedIds.length
      && score.measurements.every((measurement) =>
        Boolean(measurement.evidence_unit)
          && ["approved", "auto_admitted"].includes(measurement.admission_status)
      )
      && score.excluded_measurements.every((measurement) =>
        Boolean(measurement.evidence_unit_id)
          && Boolean(measurement.evidence_unit)
          && !["approved", "auto_admitted"].includes(measurement.admission_status)
      );
  });
}

/** Build a portable artifact without coupling the analysis tree to document text. */
export function packScoutResult(result: ScoutResponse): ResultFile<"scout", ScoutAnalysis> {
  if (!isScoutResultFinal(result) || !hasCompleteEvidenceUnitContract(result)) {
    throw new Error("Scout review is incomplete or its quantitative evidence contract is invalid");
  }
  const { blocks, ...analysis } = result;
  return {
    schema: RESULT_SCHEMA,
    version: RESULT_VERSION,
    state: "final",
    result_type: "scout",
    analysis,
    source_documents: groupDocuments(blocks),
  };
}

/** Stable, filesystem-safe name derived from the analyzed source document. */
export function scoutResultFilename(result: ScoutResponse): string {
  const documentIds = Array.from(
    new Set((result.blocks ?? []).map((block) => block.doc_id.trim()).filter(Boolean)),
  );
  const fallback = [result.indication, result.source_type].filter(Boolean).join("-") || "analysis";
  const primary = safeFilenamePart(documentIds[0] || fallback);
  const scope = documentIds.length > 1
    ? `${primary}-plus-${documentIds.length - 1}-more`
    : primary;
  return `${scope}-scout.json`;
}

function safeFilenamePart(value: string): string {
  const normalized = value
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-zA-Z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .toLowerCase();
  return (normalized || "analysis").slice(0, 96).replace(/-+$/g, "");
}

export function packInspectorResult(
  result: InspectorResponse,
): ResultFile<"inspector", InspectorAnalysis> {
  const { blocks, ...inspection } = result.inspection;
  return {
    schema: RESULT_SCHEMA,
    version: RESULT_VERSION,
    state: "final",
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
    state: "final",
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
    const result = normalizeScoutResult(
      value.analysis,
      flattenDocuments(value.source_documents),
      value.version,
    );
    if (value.version === RESULT_VERSION && (
      !isScoutResultFinal(result)
      || !hasCompleteEvidenceUnitContract(result)
    )) {
      throw new Error("final Scout result contains an incomplete quantitative evidence contract");
    }
    return result;
  }
  if (isResultEnvelope(value)) {
    throw new Error("invalid or incomplete pdis.result envelope");
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
      return normalizeInspectorResult({
        inspection: {
          ...analysis.inspection,
          blocks,
        },
      });
    }
    // Import-only migration for saved files produced before Reviewer was
    // renamed to Inspector. Runtime components never consume this old shape.
    if (value.result_type === "reviewer") {
      const analysis = value.analysis as LegacyReviewerAnalysis;
      return normalizeInspectorResult({
        inspection: {
          ...analysis.review,
          blocks,
        },
      });
    }
    throw new Error(`expected an inspector result, received ${value.result_type}`);
  }
  if (isResultEnvelope(value)) {
    throw new Error("invalid or incomplete pdis.result envelope");
  }
  const raw = value as Partial<InspectorResponse> & {
    review?: InspectorResponse["inspection"];
  };
  const inspection = raw.inspection ?? raw.review;
  if (!inspection) {
    throw new Error("not an Inspector result file");
  }
  return normalizeInspectorResult({
    inspection: {
      ...inspection,
      blocks: Array.isArray(inspection.blocks) ? inspection.blocks : [],
    },
  });
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
  if (isResultEnvelope(value)) {
    throw new Error("invalid or incomplete pdis.result envelope");
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
    ([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, RESULT_VERSION] as const).includes(
      candidate.version as ResultVersion,
    ) &&
    (candidate.version !== RESULT_VERSION || candidate.state === "final") &&
    (candidate.result_type === "aligner" ||
      candidate.result_type === "inspector" ||
      candidate.result_type === "reviewer" ||
      candidate.result_type === "scout") &&
    candidate.analysis != null &&
    Array.isArray(candidate.source_documents)
  );
}

function isResultEnvelope(value: unknown): boolean {
  return Boolean(
    value
      && typeof value === "object"
      && (value as { schema?: unknown }).schema === RESULT_SCHEMA,
  );
}

function normalizeInspectorResult(result: InspectorResponse): InspectorResponse {
  return {
    inspection: {
      ...result.inspection,
      consistency_status: result.inspection.consistency_status ?? "unknown",
      cross_section_findings: (result.inspection.cross_section_findings ?? []).map(
        (finding) => ({
          ...finding,
          block_ids: Array.isArray(finding.block_ids) ? finding.block_ids : [],
        }),
      ),
    },
  };
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
function normalizeScoutResult(
  value: unknown,
  blocks: ContentBlock[],
  sourceVersion?: ResultVersion,
): ScoutResponse {
  const raw = (value ?? {}) as Record<string, any>;
  const assessmentsByAttribute = new Map<string, Record<string, any>>(
    (raw.assessments ?? []).map((assessment: Record<string, any>) => [
      String(assessment.attribute_ref ?? ""),
      assessment,
    ]),
  );
  const quantitativeTargetsByAttribute = new Map<string, Record<string, any>[]>();
  for (const score of raw.conformity ?? []) {
    if (!String(score.target_id ?? "").startsWith("qt-") || !score.target_quote) continue;
    const targets = quantitativeTargetsByAttribute.get(String(score.attribute_ref ?? "")) ?? [];
    targets.push({
      id: score.target_id,
      attribute_ref: score.attribute_ref,
      expression: {
        kind: "bound",
        value: score.target_value,
        lower: null,
        upper: null,
        comparator: score.comparator,
        unit: score.unit ?? "",
      },
      role: score.target_role ?? "other",
      quote: score.target_quote,
      doc_block_ids: score.doc_block_ids ?? [],
      semantic_profile: legacySemanticProfile(String(score.attribute_ref ?? "numeric measure")),
      semantic_provenance: emptySemanticProvenance(),
      provenance_spans: [{ quote: score.target_quote, block_ids: score.doc_block_ids ?? [] }],
      ownership_reason: "Imported target predates canonical ownership arbitration.",
    });
    quantitativeTargetsByAttribute.set(String(score.attribute_ref ?? ""), targets);
  }
  return {
    ...raw,
    phase: raw.phase === "target_review" || raw.phase === "evidence_review"
      ? raw.phase
      : "final",
    context_validation: raw.context_validation ?? {
      status: "not_checked",
      configured_indication: String(raw.indication ?? ""),
      document_indication: "",
      reason: "This imported result predates document-context validation.",
      doc_block_ids: [],
    },
    quantitative_ledger: normalizeQuantitativeLedger(
      raw.quantitative_ledger,
      raw.variables ?? [],
    ),
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
    conformity: (raw.conformity ?? []).map(
      (score: Record<string, any>, index: number) => normalizeConformity(
        score,
        index,
        sourceVersion == null
          || sourceVersion < SCOUT_QUANTITATIVE_CONTRACT_SINCE_VERSION,
        sourceVersion == null
          || sourceVersion < SCOUT_ADMISSION_CONTRACT_SINCE_VERSION,
        sourceVersion == null
          || sourceVersion < SCOUT_EVIDENCE_UNIT_CONTRACT_SINCE_VERSION,
      ),
    ),
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
      target_ids: trace.target_ids ?? [],
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
        document_spans:
          sourceVersion != null
            && sourceVersion >= SCOUT_CLAIM_CONTRACT_SINCE_VERSION
            && Array.isArray(variable.document_spans)
            ? variable.document_spans
            : [],
        definition_mode: definitionMode,
        evidence_domain: variable.evidence_domain ?? "general",
        entities: Array.isArray(variable.entities) ? variable.entities : [],
        quantitative_targets: (
          Array.isArray(variable.quantitative_targets)
            ? variable.quantitative_targets
            : quantitativeTargetsByAttribute.get(String(variable.name ?? "")) ?? []
        ).map((target: Record<string, any>) => ({
          ...target,
          expression: target.expression ?? {
            kind: "bound",
            value: target.value ?? null,
            lower: null,
            upper: null,
            comparator: target.comparator ?? "",
            unit: target.unit ?? "",
          },
          semantic_profile: normalizeSemanticProfile(
            target.semantic_profile,
            String(target.label ?? variable.name ?? "numeric measure"),
          ),
          comparison_dimensions: Array.isArray(target.comparison_dimensions)
            ? target.comparison_dimensions
            : ["measure"],
          semantic_provenance: normalizeSemanticProvenance(target.semantic_provenance),
          provenance_spans: Array.isArray(target.provenance_spans)
            ? target.provenance_spans
            : [{ quote: target.quote ?? "", block_ids: target.doc_block_ids ?? [] }],
          ownership_reason: target.ownership_reason
            ?? "Imported target predates canonical ownership arbitration.",
          ai_recommendation: target.ai_recommendation ?? "flag",
          ai_review_reason: target.ai_review_reason
            ?? "This imported target predates independent AI review.",
          review_status: target.review_status ?? "approved",
        })),
        quantitative_statement_dispositions: Array.isArray(
          variable.quantitative_statement_dispositions,
        ) ? variable.quantitative_statement_dispositions.map(
          (disposition: Record<string, any>) => ({
            ...disposition,
            attribute_ref: disposition.attribute_ref ?? String(variable.name ?? ""),
          }),
        ) : [],
        quantitative_target_status: variable.quantitative_target_status
          ?? ((Array.isArray(variable.quantitative_targets)
            ? variable.quantitative_targets
            : quantitativeTargetsByAttribute.get(String(variable.name ?? "")) ?? []).length > 0
            ? "present"
            : "not_evaluated"),
        quantitative_target_status_reason: variable.quantitative_target_status_reason
          ?? "This imported result predates explicit numeric-target status.",
        target_resolved:
          sourceVersion != null
            && sourceVersion >= SCOUT_CLAIM_CONTRACT_SINCE_VERSION
            && typeof variable.target_resolved === "boolean"
            ? variable.target_resolved
            : false,
        target_resolution_reason:
          sourceVersion != null
            && sourceVersion >= SCOUT_CLAIM_CONTRACT_SINCE_VERSION
            ? String(variable.target_resolution_reason ?? "")
            : "This imported result predates traced document-claim resolution.",
      };
    }),
    matches: (raw.matches ?? []).map((match: Record<string, any>) => ({
      ...match,
      insight: {
        ...(match.insight ?? {}),
        retrieval_target_ids: match.insight?.retrieval_target_ids ?? [],
      },
    })),
    blocks,
  } as ScoutResponse;
}

function normalizeQuantitativeLedger(
  value: unknown,
  variables: Record<string, any>[],
): ScoutResponse["quantitative_ledger"] {
  const raw = value as Record<string, any> | null | undefined;
  if (raw && Array.isArray(raw.reviews) && Array.isArray(raw.targets)) {
    return {
      status: raw.status === "complete" || raw.status === "not_applicable"
        ? raw.status
        : "uncertain",
      reason: String(raw.reason ?? ""),
      block_ids: Array.isArray(raw.block_ids) ? raw.block_ids : [],
      reviews: raw.reviews.map((review: Record<string, any>) => ({
        unit_id: String(review.unit_id ?? ""),
        block_id: String(review.block_id ?? ""),
        quote: String(review.quote ?? ""),
        classification: review.classification,
        reason: String(review.reason ?? ""),
        attribute_ref: String(review.attribute_ref ?? ""),
        target_ids: Array.isArray(review.target_ids) ? review.target_ids : [],
        review_status: review.review_status ?? "resolved",
      })),
      targets: raw.targets.map((target: Record<string, any>) => ({
        ...target,
        ai_recommendation: target.ai_recommendation ?? "flag",
        ai_review_reason: target.ai_review_reason
          ?? "This imported target predates independent AI review.",
        review_status: target.review_status ?? "approved",
      })) as ScoutResponse["quantitative_ledger"]["targets"],
    };
  }
  const targets = variables.flatMap((variable) =>
    Array.isArray(variable.quantitative_targets) ? variable.quantitative_targets : []
  );
  return {
    status: targets.length > 0 ? "uncertain" : "not_applicable",
    reason: targets.length > 0
      ? "This imported result predates the canonical document-first quantitative ledger."
      : "This imported result contains no canonical quantitative ledger.",
    block_ids: [],
    reviews: [],
    targets: targets.map((target: Record<string, any>) => ({
      ...target,
      ai_recommendation: target.ai_recommendation ?? "flag",
      ai_review_reason: target.ai_review_reason
        ?? "This imported target predates independent AI review.",
      review_status: target.review_status ?? "approved",
    })) as ScoutResponse["quantitative_ledger"]["targets"],
  };
}

function normalizeConformity(
  score: Record<string, any>,
  index: number,
  contractPredatesCurrent: boolean,
  predatesAdmissionContract: boolean,
  predatesEvidenceUnitContract: boolean,
): Record<string, unknown> {
  const {
    conformity: _legacyConformity,
    lower: _legacyLower,
    upper: _legacyUpper,
    weighted_target_meeting_rate: _legacyWeightedRate,
    ...currentScore
  } = score;
  const rawMeasurements: Record<string, any>[] = score.measurements ?? [];
  const rawExcludedMeasurements: Record<string, any>[] = score.excluded_measurements ?? [];
  const normalizedIncluded: Record<string, any>[] = rawMeasurements.map(
    (measurement: Record<string, any>) => normalizeMeasurement(measurement, score.unit),
  );
  const normalizedExcluded: Record<string, any>[] = rawExcludedMeasurements.map(
    (measurement: Record<string, any>) => normalizeMeasurement(measurement, score.unit),
  );
  const requiresAdmissionMigration = predatesAdmissionContract && !contractPredatesCurrent;
  const measurements = requiresAdmissionMigration ? [] : normalizedIncluded;
  const excludedMeasurements = requiresAdmissionMigration
    ? [...normalizedIncluded, ...normalizedExcluded].map((measurement) => ({
        ...measurement,
        admission_status: "needs_review",
        admission_reason: "Imported prose-derived candidate requires explicit review.",
        inclusion_reason: "",
      }))
    : normalizedExcluded;
  const values = measurements
    .map((measurement: Record<string, any>) => Number(measurement.expression?.value))
    .filter(Number.isFinite)
    .sort((left: number, right: number) => left - right);
  const target = Number(score.target_value);
  const rawPercentile = values.length > 0 && Number.isFinite(target)
    ? empiricalPercentile(values, target)
    : null;
  const ambitionPercentile = rawPercentile == null
    ? null
    : score.comparator === "="
      ? null
    : score.comparator === "<=" || score.comparator === "<"
      ? 1 - rawPercentile
      : rawPercentile;
  const count = values.length;
  const targetMeetingCount = values.filter((value) => {
    if (score.comparator === "<") return value < target;
    if (score.comparator === "<=") return value <= target;
    if (score.comparator === ">") return value > target;
    if (score.comparator === ">=") return value >= target;
    return value === target;
  }).length;
  const targetMeetingRate = count > 0 ? targetMeetingCount / count : 0;
  const legacyUnverified = contractPredatesCurrent
    || predatesEvidenceUnitContract
    || !score.target_id
    || !score.target_quote || [
    ...rawMeasurements,
    ...rawExcludedMeasurements,
  ].some(
    (measurement) => !measurement.candidate_id
      || !measurement.source_quote
      || !measurement.semantic_assessment
      || !measurement.evidence_unit_id
      || !measurement.evidence_unit
      || measurement.expression?.kind === "unknown",
  );

  return {
    ...currentScore,
    target_id: score.target_id ?? `legacy-target-${index + 1}`,
    target_role: score.target_role ?? "other",
    target_quote: score.target_quote ?? "",
    verdict: requiresAdmissionMigration ? "No admitted comparators" : score.verdict,
    target_meeting_count: requiresAdmissionMigration
      ? targetMeetingCount
      : score.target_meeting_count ?? targetMeetingCount,
    target_meeting_rate: requiresAdmissionMigration
      ? targetMeetingRate
      : score.target_meeting_rate ?? targetMeetingRate,
    benchmark_count: requiresAdmissionMigration ? count : score.benchmark_count ?? count,
    benchmark_minimum: requiresAdmissionMigration
      ? null
      : score.benchmark_minimum ?? (count ? values[0] : null),
    benchmark_maximum: requiresAdmissionMigration
      ? null
      : score.benchmark_maximum ?? (count ? values[count - 1] : null),
    benchmark_mean: requiresAdmissionMigration
      ? null
      : score.benchmark_mean ?? (count ? values.reduce((sum, value) => sum + value, 0) / count : null),
    benchmark_median: requiresAdmissionMigration
      ? null
      : score.benchmark_median ?? quantile(values, 0.5),
    benchmark_lower_quartile: requiresAdmissionMigration
      ? null
      : score.benchmark_lower_quartile ?? quantile(values, 0.25),
    benchmark_upper_quartile: requiresAdmissionMigration
      ? null
      : score.benchmark_upper_quartile ?? quantile(values, 0.75),
    benchmark_standard_deviation: requiresAdmissionMigration
      ? null
      : score.benchmark_standard_deviation ?? sampleStandardDeviation(values),
    target_percentile: requiresAdmissionMigration ? null : score.target_percentile ?? rawPercentile,
    ambition_percentile: requiresAdmissionMigration ? null : score.ambition_percentile ?? ambitionPercentile,
    calibration_status: legacyUnverified
      ? "legacy_unverified"
      : requiresAdmissionMigration
        ? "insufficient"
        : score.calibration_status ?? (count >= 5 ? "sufficient" : count >= 2 ? "limited" : "insufficient"),
    doc_block_ids: score.doc_block_ids ?? [],
    measurements,
    excluded_measurements: excludedMeasurements,
    source_dispositions: Array.isArray(score.source_dispositions)
      ? score.source_dispositions
      : [],
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
    study_design: _legacyStudyDesign,
    publication_status: _legacyPublicationStatus,
    evidence_type: _legacyEvidenceType,
    source_type: _legacySourceType,
    weight: _legacyWeight,
    source_ownership: legacySourceOwnership,
    comparability: legacyComparability,
    semantic_profile: legacySourceProfile,
    semantic_assessment: currentSemanticAssessment,
    ...current
  } = measurement;
  return {
    ...current,
    candidate_id: current.candidate_id ?? "",
    expression: current.expression ?? {
      kind: current.expression_kind ?? "unknown",
      unit: current.unit ?? (typeof targetUnit === "string" ? targetUnit : ""),
      value: Number.isFinite(Number(current.value)) ? Number(current.value) : null,
      lower: null,
      upper: null,
      comparator: "",
    },
    insight_id: current.insight_id ?? "",
    source_quote: current.source_quote ?? "",
    source_record_id: current.source_record_id ?? "",
    source_identity_status: current.source_identity_status ?? "url_fallback",
    evidence_unit_id: current.evidence_unit_id ?? current.source_record_id ?? "",
    evidence_unit: current.evidence_unit ?? {
      status: "record_level",
      group: { state: "not_specified", value: "", other: "" },
      cohort: { state: "not_specified", value: "", other: "" },
      reason: "Imported measurement predates independent evidence-unit identity.",
    },
    semantic_assessment: normalizeMeasurementSemanticAssessment(
      currentSemanticAssessment,
      legacySourceOwnership,
      legacyComparability,
      legacySourceProfile,
    ),
    semantic_status: current.semantic_status ?? "unknown",
    semantic_reason: current.semantic_reason ?? "Imported measurement predates semantic normalization.",
    evidence_mode: current.evidence_mode ?? "prose",
    ai_recommendation: current.ai_recommendation ?? "flag",
    ai_review_reason: current.ai_review_reason
      ?? "This imported measurement predates independent AI evidence review.",
    admission_status: current.admission_status ?? "needs_review",
    admission_reason: current.admission_reason ?? "Imported prose-derived candidate requires review.",
    inclusion_reason: current.inclusion_reason ?? "",
    exclusion_reasons: current.exclusion_reasons ?? [],
    age_months: current.age_months ?? null,
  };
}

function legacyTernaryDecision(reason: string): Record<string, string> {
  return { state: "unknown", reason };
}

function legacyMeasurementSemanticAssessment(
  ownership: Record<string, any> | undefined,
  comparability: Record<string, any> | undefined,
  sourceProfile: Record<string, any> | undefined,
): Record<string, unknown> {
  const profile = normalizeSemanticProfile(sourceProfile, "numeric measure");
  const fields = semanticFields();
  return {
    source_ownership: ownership ?? legacyTernaryDecision(
      "Imported measurement predates source-ownership validation.",
    ),
    dimensions: Object.fromEntries(fields.map((field) => [field, {
      source: profile[field],
      compatibility: comparability?.[field] ?? legacyTernaryDecision(
        `Imported measurement predates ${field.replace("_", " ")} compatibility validation.`,
      ),
    }])),
  };
}

function normalizeMeasurementSemanticAssessment(
  current: Record<string, any> | undefined,
  ownership: Record<string, any> | undefined,
  comparability: Record<string, any> | undefined,
  sourceProfile: Record<string, any> | undefined,
): Record<string, unknown> {
  if (!current) {
    return legacyMeasurementSemanticAssessment(ownership, comparability, sourceProfile);
  }
  const fallbackProfile = normalizeSemanticProfile(sourceProfile, "numeric measure");
  return {
    source_ownership: current.source_ownership ?? legacyTernaryDecision(
      "Imported measurement predates source-ownership validation.",
    ),
    dimensions: Object.fromEntries(semanticFields().map((field) => [field, {
      source: current.dimensions?.[field]?.source ?? fallbackProfile[field],
      compatibility: current.dimensions?.[field]?.compatibility ?? legacyTernaryDecision(
        `Imported measurement predates ${field.replace("_", " ")} compatibility validation.`,
      ),
    }])),
  };
}

function legacySemanticProfile(measure: string): Record<string, unknown> {
  const unknown = { state: "unknown", value: "", other: "" };
  return {
    measure: { state: "specified", value: measure || "numeric measure", other: "" },
    endpoint: { ...unknown },
    intervention: { ...unknown },
    population: { ...unknown },
    regimen: { ...unknown },
    time_horizon: { ...unknown },
    statistic: { ...unknown },
    conditions: { ...unknown },
  };
}

function normalizeSemanticProfile(
  profile: Record<string, any> | undefined,
  measure: string,
): Record<string, unknown> {
  return { ...legacySemanticProfile(measure), ...(profile ?? {}) };
}

function semanticFields(): string[] {
  return [
    "measure", "endpoint", "intervention", "population", "regimen",
    "time_horizon", "statistic", "conditions",
  ];
}

function emptySemanticProvenance(): Record<string, unknown[]> {
  return Object.fromEntries(semanticFields().map((field) => [field, []]));
}

function normalizeSemanticProvenance(value: unknown): Record<string, unknown[]> {
  const raw = value && typeof value === "object" ? value as Record<string, unknown> : {};
  return Object.fromEntries(semanticFields().map((field) => [
    field,
    Array.isArray(raw[field]) ? raw[field] : [],
  ]));
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
