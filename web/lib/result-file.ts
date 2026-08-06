import type { AlignerResponse, ContentBlock, InspectorResponse, ScoutResponse } from "./api";

const RESULT_SCHEMA = "pdis.result" as const;

type ResultType = "aligner" | "inspector" | "scout";

/**
 * The wrapper every tool shares: how documents are separated from analysis.
 *
 * Bump this only when that wrapper changes, which invalidates every tool's saved
 * results because none of them can be read.
 */
const ENVELOPE_VERSION = 1 as const;

/**
 * Each tool's own analysis shape.
 *
 * Bump one entry when that tool's result changes. Only its files become
 * unreadable - which is the question a version is actually answering: can this
 * code read this file? That is per tool, because the three shapes are
 * independent.
 *
 * This replaced a single number stamped on all three, so an Inspector change
 * rejected saved Scout and Aligner results that were still perfectly readable.
 * The counters restart at 1 rather than continuing that number, because they mean
 * something narrower than it did and continuing its count would imply otherwise.
 */
const ANALYSIS_VERSIONS = {
  aligner: 1,
  inspector: 2,
  scout: 1,
} as const satisfies Record<ResultType, number>;

type SourceDocument = {
  doc_id: string;
  blocks: ContentBlock[];
};

type ResultFile<TResultType extends ResultType, TAnalysis> = {
  schema: typeof RESULT_SCHEMA;
  envelope_version: typeof ENVELOPE_VERSION;
  analysis_version: (typeof ANALYSIS_VERSIONS)[TResultType];
  state: "final";
  result_type: TResultType;
  analysis: TAnalysis;
  source_documents: SourceDocument[];
};

type ScoutAnalysis = Omit<ScoutResponse, "blocks">;
type InspectorAnalysis = {
  inspection: Omit<InspectorResponse["inspection"], "blocks">;
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
    return admittedIds.every(Boolean)
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

function semanticFields(): string[] {
  return [
    "measure", "endpoint", "intervention", "population", "regimen",
    "time_horizon", "statistic", "conditions",
  ];
}

function hasCompleteComparisonContract(value: unknown): boolean {
  const result = value as { quantitative_ledger?: { targets?: unknown } } | null;
  const targets = result?.quantitative_ledger?.targets;
  if (!Array.isArray(targets)) return false;
  const fields = semanticFields();
  return targets.every((target) => {
    if (!target || typeof target !== "object") return false;
    const contract = (target as Record<string, unknown>).comparison_contract;
    if (!contract || typeof contract !== "object" || Array.isArray(contract)) return false;
    const rules = contract as Record<string, unknown>;
    if (Object.keys(rules).length !== fields.length || fields.some((field) => !(field in rules))) {
      return false;
    }
    return fields.every((field) => {
      const rule = rules[field] as Record<string, unknown> | null;
      if (!rule || typeof rule !== "object" || Array.isArray(rule)) return false;
      const mode = rule.mode;
      const scope = typeof rule.scope === "string" ? rule.scope.trim() : "";
      const reason = typeof rule.reason === "string" ? rule.reason.trim() : "";
      if (!["exact", "compatible", "unconstrained", "unknown"].includes(String(mode))) {
        return false;
      }
      if (field === "measure" && mode !== "exact") return false;
      if ((mode === "exact" || mode === "compatible") && !scope) return false;
      if (mode === "unconstrained" && scope) return false;
      return mode !== "unknown" || Boolean(reason);
    });
  });
}

function hasCompleteProjectionRoleContract(value: unknown): boolean {
  const result = value as {
    development_landscape?: unknown;
    safety_observations?: unknown;
  } | null;
  const sourceRoles = new Set([
    "experimental", "comparator", "control", "co_intervention", "unknown",
  ]);
  const relationships = new Set([
    "direct", "analogous", "adjacent", "unrelated", "unknown",
  ]);
  const projections = [result?.development_landscape, result?.safety_observations];
  return projections.every((items) => Array.isArray(items) && items.every((item) => {
    if (!item || typeof item !== "object" || Array.isArray(item)) return false;
    const projection = item as Record<string, unknown>;
    return typeof projection.projection_id === "string"
      && Boolean(projection.projection_id.trim())
      && sourceRoles.has(String(projection.source_role))
      && relationships.has(String(projection.target_relationship))
      && typeof projection.target_relationship_reason === "string";
  }));
}

function hasCompleteSafetyObservationContract(value: unknown): boolean {
  const recordTypes = new Set([
    "label_warning", "reported_event", "device_event", "recall",
  ]);
  const sourceSystems = new Set([
    "fda_label", "faers", "maude", "fda_recall",
  ]);
  const visit = (node: unknown): boolean => {
    if (Array.isArray(node)) return node.every(visit);
    if (!node || typeof node !== "object") return true;
    const record = node as Record<string, unknown>;
    const observations = record.safety_observations;
    if (observations !== undefined) {
      if (!Array.isArray(observations) || !observations.every((item) => {
        if (!item || typeof item !== "object" || Array.isArray(item)) return false;
        const observation = item as Record<string, unknown>;
        const count = observation.report_count;
        const sourceSystem = String(observation.source_system);
        const validCount = sourceSystem === "faers"
          ? Number.isInteger(count) && Number(count) >= 0
          : count === null;
        return typeof observation.product_name === "string"
          && Boolean(observation.product_name.trim())
          && recordTypes.has(String(observation.record_type))
          && sourceSystems.has(sourceSystem)
          && typeof observation.label === "string"
          && Boolean(observation.label.trim())
          && typeof observation.detail === "string"
          && validCount
          && typeof observation.qualification === "string";
      })) return false;
    }
    return Object.values(record).every(visit);
  };
  return visit(value);
}

/** Build a portable artifact without coupling the analysis tree to document text. */
export function packScoutResult(result: ScoutResponse): ResultFile<"scout", ScoutAnalysis> {
  if (
    !isScoutResultFinal(result)
    || !hasCompleteComparisonContract(result)
    || !hasCompleteEvidenceUnitContract(result)
    || !hasCompleteProjectionRoleContract(result)
    || !hasCompleteSafetyObservationContract(result)
  ) {
    if (!hasCompleteSafetyObservationContract(result)) {
      throw new Error("Scout result has an incomplete safety observation contract");
    }
    throw new Error("Scout review is incomplete or its quantitative evidence contract is invalid");
  }
  const { blocks, ...analysis } = result;
  return {
    schema: RESULT_SCHEMA,
    envelope_version: ENVELOPE_VERSION,
    analysis_version: ANALYSIS_VERSIONS.scout,
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
  if (!isInspectorResultFinal(result)) {
    throw new Error("Inspector grading is incomplete and cannot be exported as a final result");
  }
  const { blocks, ...inspection } = result.inspection;
  return {
    schema: RESULT_SCHEMA,
    envelope_version: ENVELOPE_VERSION,
    analysis_version: ANALYSIS_VERSIONS.inspector,
    state: "final",
    result_type: "inspector",
    analysis: { inspection },
    source_documents: groupDocuments(blocks),
  };
}

export function isInspectorResultFinal(result: InspectorResponse): boolean {
  return result.inspection.assessment_status === "complete";
}

export function inspectorResultFilename(result: InspectorResponse): string {
  return `${safeFilenamePart(result.inspection.doc_id || "document")}-inspector.json`;
}

export function packAlignerResult(
  result: AlignerResponse,
): ResultFile<"aligner", AlignerAnalysis> {
  const { blocks, ...alignment } = result.alignment;
  return {
    schema: RESULT_SCHEMA,
    envelope_version: ENVELOPE_VERSION,
    analysis_version: ANALYSIS_VERSIONS.aligner,
    state: "final",
    result_type: "aligner",
    analysis: { alignment },
    source_documents: groupDocuments(blocks),
  };
}

export function alignerResultFilename(result: AlignerResponse): string {
  const reference = safeFilenamePart(result.alignment.reference_document.doc_id || "reference");
  const comparison = safeFilenamePart(result.alignment.comparison_document.doc_id || "comparison");
  return `${reference}-to-${comparison}-aligner.json`;
}

/** Read a final result produced by the current application contract. */
export function unpackScoutResult(value: unknown): ScoutResponse {
  const file = requireResultFile(value, "scout");
  const result = {
    ...(file.analysis as ScoutAnalysis),
    blocks: flattenDocuments(file.source_documents),
  } as ScoutResponse;
  if (
    !isScoutResultFinal(result)
    || !hasCompleteComparisonContract(result)
    || !hasCompleteEvidenceUnitContract(result)
  ) {
    throw new Error("final Scout result contains an incomplete quantitative evidence contract");
  }
  if (!hasCompleteProjectionRoleContract(result)) {
    throw new Error("final Scout result contains an incomplete projection role contract");
  }
  if (!hasCompleteSafetyObservationContract(result)) {
    throw new Error("final Scout result contains an incomplete safety observation contract");
  }
  return result;
}

export function unpackInspectorResult(value: unknown): InspectorResponse {
  const file = requireResultFile(value, "inspector");
  const analysis = file.analysis as InspectorAnalysis;
  if (!analysis.inspection) throw new Error("not an Inspector result file");
  const result = {
    inspection: {
      ...analysis.inspection,
      blocks: flattenDocuments(file.source_documents),
    },
  };
  if (!isInspectorResultFinal(result)) {
    throw new Error("final Inspector result contains incomplete grading");
  }
  return result;
}

export function unpackAlignerResult(value: unknown): AlignerResponse {
  const file = requireResultFile(value, "aligner");
  const analysis = file.analysis as AlignerAnalysis;
  if (!analysis.alignment) throw new Error("not an Aligner result file");
  return {
    alignment: {
      ...analysis.alignment,
      blocks: flattenDocuments(file.source_documents),
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

/**
 * Read a saved file, failing with the reason a reader can act on.
 *
 * The two versions are checked separately and reported separately, because they
 * call for different things: an envelope change means every saved result must be
 * re-run, while an analysis change means only this tool's must. A single message
 * covering both told everyone to re-run everything.
 */
function requireResultFile(
  value: unknown,
  expected: ResultType,
): ResultFile<ResultType, unknown> {
  if (!value || typeof value !== "object") {
    throw new Error(`expected a ${expected} result file`);
  }
  const candidate = value as Partial<ResultFile<ResultType, unknown>> & {
    result_type?: string;
  };
  if (candidate.schema !== RESULT_SCHEMA) {
    throw new Error("not a PDIS result file");
  }
  if (candidate.result_type !== expected) {
    throw new Error(
      `expected a ${expected} result, received ${candidate.result_type ?? "nothing"}`,
    );
  }
  if (candidate.envelope_version !== ENVELOPE_VERSION) {
    throw new Error(
      "this file uses an older PDIS result envelope; every saved result must be re-run",
    );
  }
  if (candidate.analysis_version !== ANALYSIS_VERSIONS[expected]) {
    throw new Error(
      `this file predates the current ${expected} result contract; re-run the ${expected} analysis`,
    );
  }
  if (
    candidate.state !== "final"
    || candidate.analysis == null
    || !Array.isArray(candidate.source_documents)
  ) {
    throw new Error(`expected a complete, final ${expected} result file`);
  }
  return candidate as ResultFile<ResultType, unknown>;
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
