import type { GateReview, QuestionAssessment } from "./api.ts";
import type { DocumentAnnotation } from "./document-trace.ts";

/**
 * Projects a finished `GateReview` into shared document annotations.
 *
 * Pure and order-preserving. It selects and places the citations the result already
 * carries; it never re-assesses, re-reads prose, or infers lineage the result does
 * not hold.
 *
 * **Only answered-from-document questions appear.** The other states have no
 * lineage to place, and each for a different reason worth stating, because the
 * temptation is to anchor them somewhere and let the viewer look complete:
 *
 *   not_found        nothing was cited, so there is no passage to attach to. It
 *                    cannot be anchored at a "probable" block either — that would
 *                    invent provenance from the `likely_in` hint, which is a guess
 *                    and the whole reason that field no longer decides anything.
 *   not_applicable   no model read the question at all.
 *   answered/context the pasted text is never chunked, so it has no blocks. Placing
 *                    such an answer in the document trace would show it as
 *                    checkable against a document it was not read from.
 *
 * So the trace answers the inverse of the panels: the panels ask what became of each
 * question, this asks which passages carried an answer and what they answered. A
 * document with no marks is not a document that failed — it is one nothing was read
 * out of, and the panels are where that is accounted for.
 */

/**
 * One kind, because Expert has one thing to place: an answer read from a passage.
 *
 * Inspector's kinds are its finding reasons, and Scout's are its evidence axes, so
 * their traces filter by layer usefully. Expert's citations are all the same claim,
 * so a second kind would be a filter with nothing to separate.
 */
export type ExpertDocumentTraceKind = "answered";

export type ExpertDocumentTraceRef = {
  questionId: string;
  discipline: string;
  question: string;
  statement: string;
  pq: boolean;
};

export type ExpertDocumentAnnotation = DocumentAnnotation<
  ExpertDocumentTraceKind,
  ExpertDocumentTraceRef
>;

export function buildExpertDocumentAnnotations(
  review: GateReview,
): ExpertDocumentAnnotation[] {
  return review.disciplines.flatMap((discipline) =>
    discipline.questions
      .filter(citesADocument)
      .map((question) => ({
        id: question.id,
        kind: "answered" as const,
        layerLabel: "Answered",
        // The discipline leads, because that is what a reader scanning the gutter
        // recognises; the id qualifies it for anyone matching against the bank.
        title: `${discipline.label} · ${question.id}`,
        summary: question.statement,
        statusLabel: question.pq ? "WHO prequalification" : undefined,
        blockIds: question.cited_block_ids,
        // Expert carries no quotes, only block ids, so annotations claim whole
        // blocks. Searching block text for a phrase to underline would invent a
        // span the model never asserted.
        spans: [],
        emphasis: { tone: "neutral" as const, badge: "Answered" },
        sourceRef: {
          questionId: question.id,
          discipline: discipline.label,
          question: question.text,
          statement: question.statement,
          pq: question.pq,
        },
      })),
  );
}

function citesADocument(question: QuestionAssessment): boolean {
  return (
    question.state === "answered"
    && question.source === "document"
    && question.cited_block_ids.length > 0
  );
}

/**
 * How many questions each supplied document answered.
 *
 * Counted from the same annotations the trace renders, so the tab's count and its
 * contents cannot disagree. A document that answered nothing is still listed, at
 * zero, because its absence from the list would read as "not uploaded".
 */
export function answersPerDocument(
  review: GateReview,
): { docId: string; sourceType: string; count: number }[] {
  const byBlock = new Map<string, string>();
  for (const block of review.blocks ?? []) byBlock.set(block.id, block.doc_id);

  const counts = new Map<string, number>();
  for (const annotation of buildExpertDocumentAnnotations(review)) {
    // One question can cite passages from two documents. It counts once for each,
    // because the question here is "what did this document answer", not "how many
    // questions are there" — the panels own that total.
    for (const docId of new Set(
      annotation.blockIds.map((id) => byBlock.get(id)).filter(Boolean) as string[],
    )) {
      counts.set(docId, (counts.get(docId) ?? 0) + 1);
    }
  }

  return review.documents.map((document) => ({
    docId: document.doc_id,
    sourceType: document.source_type,
    count: counts.get(document.doc_id) ?? 0,
  }));
}
