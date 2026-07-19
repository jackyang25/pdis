import type { ContentBlock, ReviewerResponse, ScoutResponse } from "./api";

const RESULT_SCHEMA = "pdis.result" as const;
const RESULT_VERSION = 1 as const;

type ResultType = "reviewer" | "scout";

type SourceDocument = {
  doc_id: string;
  blocks: ContentBlock[];
};

type ResultFile<TResultType extends ResultType, TAnalysis> = {
  schema: typeof RESULT_SCHEMA;
  version: typeof RESULT_VERSION;
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
    const analysis = value.analysis as ScoutAnalysis;
    return { ...analysis, blocks: flattenDocuments(value.source_documents) };
  }
  const legacy = value as ScoutResponse;
  return { ...legacy, blocks: Array.isArray(legacy?.blocks) ? legacy.blocks : [] };
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
    candidate.version === RESULT_VERSION &&
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
