import type {
  AlignerResponse,
  ContentBlock,
  ExpertResponse,
  InspectorResponse,
  ScoutResponse,
} from "./api";
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
  // 3: findings returned, one per requirement, with a one-way verdict. A v2 file
  // carries no findings at all, so it would render as a run that compared nothing —
  // indistinguishable from a run that found nothing wrong.
  aligner: 3,
  // 2: five states became three. `not_answerable` and `not_assessable` were both
  // derived from a judgment about which document could answer a question — a judgment
  // the source question bank does not contain — so a v1 file describes states this
  // code has no types for, and its counts were computed on a different denominator.
  // 3: `partly_answered` joined the model's vocabulary. A v2 file has no such state
  // and its counts were computed on a binary, so its "not found" total silently
  // includes every partial answer — a different measurement, not a missing field.
  // 4: the question bank was replaced. A v3 file was triaged against a different set of
  // questions under different gate ids, with a per-question WHO-PQ marker and a hint
  // about where an answer usually lives, neither of which exists now — so it is not a
  // stale version of this review, it is a review of something else.
  expert: 4,
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
  /**
   * Who this run is, carried so a file re-imported into a workspace that already
   * holds it is recognised rather than held twice. Two runs of the same document
   * are different runs and get different identities.
   *
   * Optional on read: files written before identity existed are still readable,
   * and are given one when imported. Always written.
   */
  id?: string;
  /** ISO instant the run finished. Labels the run for a reader. */
  created_at?: string;
  analysis: TAnalysis;
  source_documents: SourceDocument[];
};

function newRunId(): string {
  return (
    globalThis.crypto?.randomUUID?.()
    ?? `run-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
  );
}

/** Identity for a newly packed run. */
function stamp(): { id: string; created_at: string } {
  return { id: newRunId(), created_at: new Date().toISOString() };
}

/**
 * The identity inside a result file, for a caller recording it in a workspace.
 *
 * Returns nothing for a file written before identity existed, so the caller
 * mints one rather than treating every such file as the same run.
 */
export function readResultIdentity(
  value: unknown,
): { id?: string; created_at?: string } {
  if (!value || typeof value !== "object") return {};
  const file = value as Partial<ResultFile<ResultType, unknown>>;
  return {
    ...(typeof file.id === "string" && file.id ? { id: file.id } : {}),
    ...(typeof file.created_at === "string" && file.created_at
      ? { created_at: file.created_at }
      : {}),
  };
}

type ScoutAnalysis = Omit<ScoutResponse, "blocks">;
type InspectorAnalysis = {
  inspection: Omit<InspectorResponse["inspection"], "blocks">;
};
type AlignerAnalysis = {
  alignment: Omit<AlignerResponse["alignment"], "blocks">;
};
type ExpertAnalysis = {
  review: Omit<ExpertResponse["review"], "blocks">;
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
    ...stamp(),
    result_type: "scout",
    analysis,
    source_documents: groupDocuments(blocks),
  };
}

/** Stable, filesystem-safe name derived from the analyzed source document. */
export function scoutResultFilename(result: ScoutResponse): string {
  return runFilename(result, "scout");
}

/**
 * Every tool that keeps finished runs.
 *
 * Wider than `ResultType`, which is the set that exports a portable file: Chunker and
 * Searcher keep runs a reader switches between without producing one.
 */
export type RunKeepingTool = ResultType | "chunker" | "searcher";

/**
 * What identifies one run, in the order a reader recognises it.
 *
 * One list per tool, feeding two things that must agree: the row in the run picker and
 * the name of the exported file. They were written separately — a lambda in the page and
 * a function here — so they drifted, and the drift was invisible from either side.
 * Expert's picker showed only the gate, so two runs of one gate on different documents
 * were two identical rows while their files differed; Aligner's picker named documents
 * and its file named types.
 *
 * The parts are readable text. `runLabel` joins them for the eye and `runFilename`
 * slugs them for a filesystem, so the two can differ in punctuation and never in
 * substance.
 */
export function runIdentity(result: unknown, type: RunKeepingTool): string[] {
  switch (type) {
    case "inspector": {
      const inspection = (result as InspectorResponse).inspection;
      return [inspection.doc_id].filter(Boolean);
    }
    case "scout": {
      const scout = result as ScoutResponse;
      const documents = Array.from(
        new Set((scout.blocks ?? []).map((block) => block.doc_id.trim()).filter(Boolean)),
      );
      if (documents.length > 1) {
        return [documents[0], `plus ${documents.length - 1} more`];
      }
      return documents.length > 0
        ? documents
        : [scout.indication, scout.source_type].filter(Boolean);
    }
    case "expert": {
      const review = (result as ExpertResponse).review;
      // The gate first, then the documents: the same set is triaged again at every gate,
      // and the same gate is run against different sets. Either alone collides.
      return [
        review.gate_label || review.gate_id,
        ...review.documents.map((document) => document.source_type || document.doc_id),
      ].filter(Boolean);
    }
    case "aligner": {
      const alignment = (result as AlignerResponse).alignment;
      // The documents, not the comparisons: a run holds any number of either, and the
      // documents are what a reader recognises.
      return alignment.documents
        .map((document) => document.source_type || document.doc_id)
        .filter(Boolean);
    }
    case "chunker": {
      const parsed = result as { doc_id?: string };
      return [parsed.doc_id].filter(Boolean) as string[];
    }
    case "searcher": {
      // The query is the run. Searcher exports no file, so nothing here has a filename
      // to agree with — it is on this path because a picker row is a picker row, and one
      // page naming its runs its own way is how the last inconsistency started.
      return [(result as { query?: string }).query].filter(Boolean) as string[];
    }
  }
}

/** One run named for the eye: the picker row, and nothing else. */
export function runLabel(result: unknown, type: RunKeepingTool): string {
  const parts = runIdentity(result, type);
  return parts.length > 0 ? parts.join(" · ") : FALLBACK_LABEL[type];
}

/** The same run named for a filesystem, with the tool that produced it. */
export function runFilename(result: unknown, type: RunKeepingTool): string {
  const parts = runIdentity(result, type).map(safeFilenamePart).filter(Boolean);
  return `${parts.join("-") || type}-${type}.json`;
}

/**
 * What to call a run that identifies itself with nothing.
 *
 * Per tool, because "Inspection" and "Gate review" are what the tool calls its own work
 * and a shared word for all of them would be less use than the tool's own.
 */
const FALLBACK_LABEL: Record<RunKeepingTool, string> = {
  inspector: "Inspection",
  scout: "Scout result",
  expert: "Gate review",
  aligner: "Alignment",
  chunker: "Parsed document",
  searcher: "Search",
};

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
    ...stamp(),
    result_type: "inspector",
    analysis: { inspection },
    source_documents: groupDocuments(blocks),
  };
}

export function isInspectorResultFinal(result: InspectorResponse): boolean {
  return result.inspection.assessment_status === "complete";
}

export function inspectorResultFilename(result: InspectorResponse): string {
  return runFilename(result, "inspector");
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
    ...stamp(),
    result_type: "aligner",
    analysis: { alignment },
    source_documents: groupDocuments(blocks),
  };
}

export function packExpertResult(
  result: ExpertResponse,
): ResultFile<"expert", ExpertAnalysis> {
  RESULT_CONTRACTS.expert(result);
  const { blocks, ...review } = result.review;
  return {
    schema: RESULT_SCHEMA,
    envelope_version: ENVELOPE_VERSION,
    analysis_version: ANALYSIS_VERSIONS.expert,
    state: "final",
    ...stamp(),
    result_type: "expert",
    analysis: { review },
    source_documents: groupDocuments(blocks),
  };
}

export function expertResultFilename(result: ExpertResponse): string {
  return runFilename(result, "expert");
}

export function alignerResultFilename(result: AlignerResponse): string {
  return runFilename(result, "aligner");
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

export function unpackExpertResult(value: unknown): ExpertResponse {
  const file = requireResultFile(value, "expert");
  const analysis = file.analysis as ExpertAnalysis;
  const result = {
    review: {
      ...(analysis.review ?? {}),
      blocks: flattenDocuments(file.source_documents),
    },
  } as ExpertResponse;
  RESULT_CONTRACTS.expert(result);
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
