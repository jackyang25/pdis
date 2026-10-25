import type {
  AlignerResponse,
  ContentBlock,
  DraftResult,
  ScreenerResponse,
  InspectorResponse,
  ScoutResponse,
} from "./api";
import { displayLabel } from "./display-label.ts";
import { RESULT_CONTRACTS, type ResultType } from "./result-contracts.ts";
import { formatWindowDate } from "./published-date.ts";
import { countLabel } from "./count-label.ts";

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
  // 4: visual references are separate from exact text quotations.
  aligner: 4,
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
  // 5: every answer cites retained document blocks. Older context answers carry only
  // labels, so their missing evidence cannot be reconstructed during import.
  screener: 5,
  // 4: a failed consistency pass carries `consistency_failure_code`. A v3 file records the
  // failure as prose alone, and no code can be recovered from prose without inventing one.
  inspector: 4,
  // 2: explicit review/mapping failures, retained reviewer source context,
  // and model-authored numeric presentation metadata.
  // 3: a stage that obtained no verdict records `not_assessed` with a failure code, where
  // a v2 file filed it under `unrelated`, `unknown` or `uncertain` - a failed call read as
  // the model's answer. A numeric review names its failed checks by code, and a meeting
  // rate without a cohort is null rather than zero.
  // 4: every searchable field holds a grounding and a precedent, `no_evidence` where nothing
  // retrieved reached it, and a run states its retrieval scope and identity-layer outcomes.
  // 5: the reviewer chooses which fields are searched. `not_searched_fields` records the
  // choice and those fields hold `not_searched`; a v4 file has neither, and its every field
  // was searched under a contract that did not say so.
  scout: 5,
  // 2: a failed call carries its `cause` code, and quotes a reader offered that its excerpt
  // does not contain are counted. A v1 file has neither, and its silence on the second
  // would read as "every quote was found".
  // 3: a number carries the quote's own words for it (`value.text`), and each figure group
  // names the observations it was computed from. A v2 number was never checked against its
  // quote, so it cannot be read as one that was.
  // 4: each observation carries its source's publication date at the stated precision, which
  // the suggestion weighed. A v3 file has none, and its silence would read as "undated".
  drafter: 4,
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

/**
 * Who a held run is: the workspace entry's own identity, written into its file.
 *
 * Taken from the entry rather than minted at packing. A file that named a fresh id
 * every time it was written was a stranger to the workspace that wrote it, so
 * re-importing a run just downloaded held it twice.
 */
export type RunIdentity = { id: string; created_at: string };

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
type ScreenerAnalysis = {
  review: Omit<ScreenerResponse["review"], "blocks">;
};

/** Build a portable artifact without coupling the analysis tree to document text. */
export function packScoutResult(result: ScoutResponse, identity: RunIdentity): ResultFile<"scout", ScoutAnalysis> {
  // The same contract the import path runs, so a file we could not read is never
  // written in the first place.
  RESULT_CONTRACTS.scout(result);
  const { blocks, ...analysis } = result;
  return {
    schema: RESULT_SCHEMA,
    envelope_version: ENVELOPE_VERSION,
    analysis_version: ANALYSIS_VERSIONS.scout,
    state: "final",
    id: identity.id,
    created_at: identity.created_at,
    result_type: "scout",
    analysis,
    source_documents: groupDocuments(blocks),
  };
}

/** A draft reads no document, so the analysis is the whole result and no documents travel. */
type DrafterAnalysis = DraftResult;

export function packDrafterResult(result: DraftResult, identity: RunIdentity): ResultFile<"drafter", DrafterAnalysis> {
  RESULT_CONTRACTS.drafter(result);
  return {
    schema: RESULT_SCHEMA,
    envelope_version: ENVELOPE_VERSION,
    analysis_version: ANALYSIS_VERSIONS.drafter,
    state: "final",
    id: identity.id,
    created_at: identity.created_at,
    result_type: "drafter",
    analysis: result,
    source_documents: [],
  };
}

export function unpackDrafterResult(value: unknown): DraftResult {
  const file = requireResultFile(value, "drafter");
  const result = file.analysis as DrafterAnalysis;
  RESULT_CONTRACTS.drafter(result);
  return result;
}

/**
 * Every tool that keeps finished runs.
 *
 * Wider than `ResultType`, which is the set that exports a portable file: Chunker and
 * Searcher keep runs a reader switches between without producing one.
 */
export type RunKeepingTool = ResultType | "chunker" | "searcher";

/**
 * The subject of a run, shared by its heading and history label.
 * Source filenames belong in Documents, not concatenated into a multi-document title.
 * Labels are presentation only: saved IDs distinguish runs, and history shows the time.
 */
function runLabelParts(result: unknown, type: RunKeepingTool): string[] {
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
    case "screener": {
      const review = (result as ScreenerResponse).review;
      return [review.gate_label || review.gate_id].filter(Boolean);
    }
    case "aligner": {
      const alignment = (result as AlignerResponse).alignment;
      // The document types, not their names: a three-document run reads as what it
      // compared rather than as two filenames with a third silently dropped.
      // A type is shown the way the rest of the suite spells it (iTPP, cTPP, IPDP); a
      // filename standing in for a missing type is shown as written.
      return alignment.documents
        .map((document) => document.source_type ? displayLabel(document.source_type) : document.doc_id)
        .filter(Boolean);
    }
    case "drafter": {
      // The disease it was drafted for; the product type is the scope line beneath.
      return [displayLabel((result as DraftResult).indication)].filter(Boolean);
    }
    case "chunker": {
      const parsed = result as { doc_id?: string };
      return [parsed.doc_id].filter(Boolean) as string[];
    }
    case "searcher": {
      // The query is what distinguishes searches in the history picker.
      return [(result as { query?: string }).query].filter(Boolean) as string[];
    }
  }
}

/** One presentation label for the result heading and history picker. */
export function runLabel(result: unknown, type: RunKeepingTool): string {
  const parts = runLabelParts(result, type);
  return parts.length > 0 ? parts.join(" · ") : FALLBACK_LABEL[type];
}

/**
 * Saved input context, not analysis outcomes: indication, intervention class and type.
 * Screener adds the supplied document count instead of naming every file in its title.
 * Full source names remain in Documents; neither label nor scope changes saved identity.
 */
export function runScope(result: unknown, type: RunKeepingTool): string {
  // Avoid repeating document types already named in Aligner's heading.
  const named = new Set(runLabelParts(result, type).map((part) => part.toLowerCase()));
  const parts = runConfiguration(result, type)
    .filter((part) => part && !named.has(part.toLowerCase()))
    .map(displayLabel);
  if (type === "screener") {
    const count = (result as ScreenerResponse).review.documents.length;
    if (count > 0) parts.push(countLabel(count, "document"));
  }
  // A publication window is scope: it removes evidence before anything is counted, so the
  // same document gives different numbers under different windows.
  if (type === "scout") {
    const since = formatWindowDate((result as ScoutResponse).published_since);
    if (since) parts.push(`evidence since ${since}`);
  }
  return parts.join(" · ");
}

function runConfiguration(result: unknown, type: RunKeepingTool): string[] {
  switch (type) {
    case "inspector": {
      const { inspection } = result as InspectorResponse;
      return [
        inspection.indication ?? "",
        inspection.intervention_class ?? "",
        inspection.source_type ?? "",
      ];
    }
    case "scout": {
      const scout = result as ScoutResponse;
      return [scout.indication, scout.intervention_class, scout.source_type];
    }
    case "screener": {
      const { review } = result as ScreenerResponse;
      return [review.indication, review.intervention_class];
    }
    case "aligner": {
      const { alignment } = result as AlignerResponse;
      return [
        alignment.indication,
        alignment.intervention_class,
        ...documentTypes(alignment.documents),
      ];
    }
    case "drafter":
      return [(result as DraftResult).intervention_class, "itpp"];
    default:
      // Chunker and searcher keep runs but hold no configuration: one parses a file, the
      // other answers a query. Neither has a scope line to state.
      return [];
  }
}

function documentTypes(documents: readonly { source_type?: string }[]): string[] {
  return Array.from(
    new Set(documents.map((document) => document.source_type ?? "").filter(Boolean)),
  );
}

/** A download suggestion only. The browser owns saving; file contents own identity. */
export function runFilename(type: Exclude<RunKeepingTool, "searcher">): string {
  return `pdis-${type}.json`;
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
  screener: "Gate review",
  aligner: "Alignment",
  drafter: "Draft iTPP",
  chunker: "Parsed document",
  searcher: "Search",
};

export function packInspectorResult(
  result: InspectorResponse,
  identity: RunIdentity,
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
    id: identity.id,
    created_at: identity.created_at,
    result_type: "inspector",
    analysis: { inspection },
    source_documents: groupDocuments(blocks),
  };
}

export function isInspectorResultFinal(result: InspectorResponse): boolean {
  return result.inspection.assessment_status === "complete";
}

export function packAlignerResult(
  result: AlignerResponse,
  identity: RunIdentity,
): ResultFile<"aligner", AlignerAnalysis> {
  RESULT_CONTRACTS.aligner(result);
  const { blocks, ...alignment } = result.alignment;
  return {
    schema: RESULT_SCHEMA,
    envelope_version: ENVELOPE_VERSION,
    analysis_version: ANALYSIS_VERSIONS.aligner,
    state: "final",
    id: identity.id,
    created_at: identity.created_at,
    result_type: "aligner",
    analysis: { alignment },
    source_documents: groupDocuments(blocks),
  };
}

export function packScreenerResult(
  result: ScreenerResponse,
  identity: RunIdentity,
): ResultFile<"screener", ScreenerAnalysis> {
  RESULT_CONTRACTS.screener(result);
  const { blocks, ...review } = result.review;
  return {
    schema: RESULT_SCHEMA,
    envelope_version: ENVELOPE_VERSION,
    analysis_version: ANALYSIS_VERSIONS.screener,
    state: "final",
    id: identity.id,
    created_at: identity.created_at,
    result_type: "screener",
    analysis: { review },
    source_documents: groupDocuments(blocks),
  };
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
  const file = requireResultFile(upgradeInspectorV2(value), "inspector");
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

/**
 * v2 already has today's verdict semantics; older verdict vocabularies stay refused.
 *
 * A v2 run whose consistency pass failed recorded no failure code, and none is invented:
 * it is left to the version gate, which asks for a re-run.
 */
function upgradeInspectorV2(value: unknown): unknown {
  if (!value || typeof value !== "object") return value;
  const file = value as Record<string, unknown>;
  if (file.schema !== RESULT_SCHEMA || file.result_type !== "inspector"
    || file.envelope_version !== ENVELOPE_VERSION || file.analysis_version !== 2) return value;
  const analysis = file.analysis as { inspection?: Record<string, unknown> } | undefined;
  if (!analysis?.inspection || !Array.isArray(analysis.inspection.sections)) return value;
  if (analysis.inspection.consistency_status === "failed") return value;
  const { sections, ...document } = analysis.inspection;
  const id = "legacy_template";
  return { ...file, analysis_version: ANALYSIS_VERSIONS.inspector, analysis: { inspection: {
    ...document,
    consistency_failure_code: null,
    applicability_facts: {},
    rubric_resolutions: [{ rubric_id: id, display_name: "Historical template review", status: "included",
      reason_code: "legacy_import", reason: "Imported single-rubric review; the original file did not record its rubric revision." }],
    reviews: [{ rubric: { id, revision: null, updated_on: null, display_name: "Historical template review",
      authority: "Template rubric (historical)", scope: "Original requirements and source revision were not saved. Re-run to assess current rubrics.",
      evidence_scope: "mapped_section", stage_guidance: "", mirrors: null, sources: [], requirements: [] },
      sections, assessment_status: document.assessment_status }],
  } } };
}

export function unpackAlignerResult(value: unknown): AlignerResponse {
  const file = requireResultFile(upgradeAlignerV3(value), "aligner");
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

/** Old text citations retain their meaning; no historical visual lineage is invented. */
function upgradeAlignerV3(value: unknown): unknown {
  if (!value || typeof value !== "object") return value;
  const file = value as Record<string, unknown>;
  if (file.schema !== RESULT_SCHEMA || file.result_type !== "aligner"
    || file.envelope_version !== ENVELOPE_VERSION || file.analysis_version !== 3) return value;
  const analysis = file.analysis as { alignment?: Record<string, unknown> } | undefined;
  if (!Array.isArray(analysis?.alignment?.findings)) return value;
  return { ...file, analysis_version: ANALYSIS_VERSIONS.aligner, analysis: {
    ...analysis, alignment: { ...analysis.alignment, findings: analysis.alignment.findings.map(item => ({
      ...item, reference_visual_block_ids: [], comparison_visual_block_ids: [],
    })) },
  } };
}

export function unpackScreenerResult(value: unknown): ScreenerResponse {
  const file = requireResultFile(value, "screener");
  const analysis = file.analysis as ScreenerAnalysis;
  const result = {
    review: {
      ...(analysis.review ?? {}),
      blocks: flattenDocuments(file.source_documents),
    },
  } as ScreenerResponse;
  RESULT_CONTRACTS.screener(result);
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
