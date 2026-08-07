import type { AlignerResponse, ContentBlock, InspectorResponse, ScoutResponse } from "./api";
import { RESULT_CONTRACTS, type ResultType } from "./result-contracts.ts";

export { isScoutResultFinal, pendingQuantitativeReviewCount } from "./result-contracts.ts";

const RESULT_SCHEMA = "pdis.result" as const;

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
  // 2: the extract-and-link analysis was removed; a result is now two identified
  // documents and their blocks. Saved v1 files describe units and relations this
  // code no longer has types for, so they cannot be rendered.
  aligner: 2,
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








/** Build a portable artifact without coupling the analysis tree to document text. */
export function packScoutResult(result: ScoutResponse): ResultFile<"scout", ScoutAnalysis> {
  // The same contract the import path runs, so a file we could not read is never
  // written in the first place.
  RESULT_CONTRACTS.scout(result);
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
  RESULT_CONTRACTS.inspector(result);
  if (!isInspectorResultFinal(result)) {
    throw new Error("this inspector result cannot be read: the run did not complete");
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
  RESULT_CONTRACTS.aligner(result);
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
  // Named by the documents rather than by the comparisons, because a run holds
  // any number of either and the documents are what a reader recognises.
  const parts = result.alignment.documents.map((document) =>
    safeFilenamePart(document.source_type || document.doc_id),
  );
  return `${parts.join("-") || "aligner"}-aligner.json`;
}

/** Read a final result produced by the current application contract. */
export function unpackScoutResult(value: unknown): ScoutResponse {
  const file = requireResultFile(value, "scout");
  const result = {
    ...(file.analysis as ScoutAnalysis),
    blocks: flattenDocuments(file.source_documents),
  } as ScoutResponse;
  RESULT_CONTRACTS.scout(result);
  return result;
}

export function unpackInspectorResult(value: unknown): InspectorResponse {
  const file = requireResultFile(value, "inspector");
  const analysis = file.analysis as InspectorAnalysis;
  const result = {
    inspection: {
      ...(analysis.inspection ?? {}),
      blocks: flattenDocuments(file.source_documents),
    },
  } as InspectorResponse;
  RESULT_CONTRACTS.inspector(result);
  if (!isInspectorResultFinal(result)) {
    throw new Error("this inspector result cannot be read: the run did not complete");
  }
  return result;
}

export function unpackAlignerResult(value: unknown): AlignerResponse {
  const file = requireResultFile(value, "aligner");
  const analysis = file.analysis as AlignerAnalysis;
  const result = {
    alignment: {
      ...(analysis.alignment ?? {}),
      blocks: flattenDocuments(file.source_documents),
    },
  } as AlignerResponse;
  RESULT_CONTRACTS.aligner(result);
  return result;
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
