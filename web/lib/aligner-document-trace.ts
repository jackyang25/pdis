import type { AlignmentFinding, AlignmentResult, AlignmentVerdict } from "./api.ts";
import {
  ALIGNMENT_VERDICTS,
  ALIGNMENT_VERDICT_TONE,
  VERDICT_LABELS,
  spanBlockIds,
} from "./api.ts";
import type {
  DocumentAnnotation,
  DocumentAnnotationEmphasis,
} from "./document-trace.ts";
import { traceSpans } from "./document-trace.ts";

/**
 * Projects a finished alignment into shared document annotations.
 *
 * Pure and order-preserving. It selects and places the citations the result already
 * carries; it never re-judges, re-reads prose, or infers lineage the result does not
 * hold.
 *
 * Aligner is the one tool whose findings have lineage on **both** sides, so each finding
 * places two annotations rather than one: the requirement, in the document that set it,
 * and the verdict, in the document measured against it. That is the honest shape — a
 * single annotation carrying blocks from two documents would let a reader open a passage
 * in the reference document and read "falls short", which is a claim about the other one.
 *
 * The two are told apart by their layer, so filtering to one side is filtering to one
 * kind of claim: what was asked, or what was found.
 *
 * A `not_addressed` finding places only its requirement. There is no passage in the
 * measured document to attach the verdict to, and anchoring it near where an answer
 * "should" have been would invent a location the model never named.
 */

/**
 * Trace layers. One per verdict, plus the requirement side.
 *
 * `requirement` is a layer rather than a badge because it answers a different question:
 * every other layer shows what a document *did* with a bar, and this one shows where the
 * bar is stated.
 */
export type AlignerDocumentTraceKind = "requirement" | AlignmentVerdict;

export type AlignerDocumentTraceRef = {
  requirementId: string;
  requirement: string;
  comparison: string;
  question: string;
  verdict: AlignmentVerdict;
  statement: string;
  /** Which side of the comparison this annotation is placed on. */
  side: "reference" | "comparison";
};

export type AlignerDocumentAnnotation = DocumentAnnotation<
  AlignerDocumentTraceKind,
  AlignerDocumentTraceRef
>;

/**
 * Which tone each verdict takes, from the set every tool's trace shares.
 *
 * `meets` and `exceeds` are `success` for the same reason Screener's `answered` is: the
 * thing asked for is there. Grey would read as "nobody looked".
 *
 * `falls_short` and `not_comparable` are caution, not danger: falling short of a target
 * is this tool's central finding and a normal state of an in-progress programme, not a
 * failure. Danger stays with a contradiction or a grade a tool calls blocking, and
 * reusing it here would make one colour mean two things across two tools.
 */
const TONE: Record<AlignmentVerdict, DocumentAnnotationEmphasis["tone"]> = Object.fromEntries(
  ALIGNMENT_VERDICTS.map((verdict) => [
    verdict,
    // The trace calls a caution `caution` and the tone scale calls it `warning`; they are
    // the same reading under two names, which is why the map above is the only place the
    // judgement is made and this is a translation rather than a second opinion.
    ALIGNMENT_VERDICT_TONE[verdict],
  ]),
) as Record<AlignmentVerdict, DocumentAnnotationEmphasis["tone"]>;

export function buildAlignerDocumentAnnotations(
  result: AlignmentResult,
): AlignerDocumentAnnotation[] {
  const edges = new Map(result.edges.map((edge) => [edge.edge_id, edge]));
  const names = new Map(
    result.documents.map((document) => [
      document.doc_id,
      document.display_name || document.source_type || document.doc_id,
    ]),
  );

  return result.findings.flatMap((finding) => {
    const edge = edges.get(finding.edge_id);
    if (!edge) return [];
    const comparison = `${names.get(edge.reference_doc_id) ?? edge.reference_doc_id} → ${
      names.get(edge.comparison_doc_id) ?? edge.comparison_doc_id
    }`;
    const ref = (side: "reference" | "comparison"): AlignerDocumentTraceRef => ({
      requirementId: finding.requirement_id,
      requirement: finding.requirement,
      comparison,
      question: edge.question,
      verdict: finding.verdict,
      statement: finding.statement,
      side,
    });

    const annotations: AlignerDocumentAnnotation[] = [];
    if (finding.reference_spans.length > 0) {
      annotations.push({
        id: `${finding.requirement_id}:requirement`,
        kind: "requirement",
        layerLabel: "Requirement",
        title: `${comparison} · ${finding.requirement_id}`,
        summary: finding.requirement,
        blockIds: spanBlockIds(finding.reference_spans),
        spans: traceSpans(finding.reference_spans),
        // Neutral: the requirement side states what was asked, and claims nothing about
        // whether it was met. The verdict on the other document carries that.
        emphasis: { tone: "neutral", badge: "Requirement" },
        sourceRef: ref("reference"),
      });
    }
    if (finding.comparison_spans.length > 0) {
      annotations.push({
        id: `${finding.requirement_id}:verdict`,
        kind: finding.verdict,
        layerLabel: VERDICT_LABELS[finding.verdict],
        title: `${comparison} · ${finding.requirement_id}`,
        summary: finding.statement,
        blockIds: spanBlockIds(finding.comparison_spans),
        spans: traceSpans(finding.comparison_spans),
        emphasis: {
          tone: TONE[finding.verdict],
          badge: VERDICT_LABELS[finding.verdict],
        },
        sourceRef: ref("comparison"),
      });
    }
    return annotations;
  });
}

/**
 * How many findings each supplied document appears in, and on which side.
 *
 * Counted from the same annotations the trace renders, so a tab's count and its contents
 * cannot disagree. A document with nothing on one side is still listed at zero, because
 * its absence would read as "not uploaded".
 */
export function findingsPerDocument(
  result: AlignmentResult,
): { docId: string; sourceType: string; requirements: number; verdicts: number }[] {
  const byBlock = new Map<string, string>();
  for (const block of result.blocks) byBlock.set(block.id, block.doc_id);

  const tally = new Map<string, { requirements: number; verdicts: number }>();
  for (const annotation of buildAlignerDocumentAnnotations(result)) {
    const side = annotation.kind === "requirement" ? "requirements" : "verdicts";
    // One annotation can cite passages in only one document, but counting through the
    // blocks keeps that a fact about the data rather than an assumption.
    for (const docId of new Set(
      annotation.blockIds.map((id) => byBlock.get(id)).filter(Boolean) as string[],
    )) {
      const entry = tally.get(docId) ?? { requirements: 0, verdicts: 0 };
      entry[side] += 1;
      tally.set(docId, entry);
    }
  }

  return result.documents.map((document) => ({
    docId: document.doc_id,
    sourceType: document.source_type,
    requirements: tally.get(document.doc_id)?.requirements ?? 0,
    verdicts: tally.get(document.doc_id)?.verdicts ?? 0,
  }));
}

/** Findings with no lineage on the measured side, which is every `not_addressed`. */
export function unplacedFindings(result: AlignmentResult): AlignmentFinding[] {
  return result.findings.filter(
    (finding) => finding.comparison_spans.length === 0,
  );
}
