import type { AlignmentResult, AlignmentVerdict } from "./api.ts";
import {
  ALIGNMENT_VERDICT_TONE,
  VERDICT_LABELS,
  alignmentBlockIds,
} from "./api.ts";
import type { DocumentAnnotation } from "./document-trace.ts";
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
    if (alignmentBlockIds(finding, "reference").length > 0) {
      annotations.push({
        id: `${finding.requirement_id}:requirement`,
        kind: "requirement",
        layerLabel: "Requirement",
        title: `${comparison} · ${finding.requirement_id}`,
        summary: finding.requirement,
        blockIds: alignmentBlockIds(finding, "reference"),
        spans: traceSpans(finding.reference_spans),
        // Neutral: the requirement side states what was asked, and claims nothing about
        // whether it was met. The verdict on the other document carries that.
        emphasis: { tone: "neutral", badge: "Requirement" },
        sourceRef: ref("reference"),
      });
    }
    if (alignmentBlockIds(finding, "comparison").length > 0) {
      annotations.push({
        id: `${finding.requirement_id}:verdict`,
        kind: finding.verdict,
        layerLabel: VERDICT_LABELS[finding.verdict],
        title: `${comparison} · ${finding.requirement_id}`,
        summary: finding.statement,
        blockIds: alignmentBlockIds(finding, "comparison"),
        spans: traceSpans(finding.comparison_spans),
        emphasis: {
          // The verdict's own tone, from the one map the count row reads: `meets` and
          // `exceeds` are success because the thing asked for is there, and falling short
          // is caution rather than danger - a normal state of an in-progress programme.
          tone: ALIGNMENT_VERDICT_TONE[finding.verdict],
          badge: VERDICT_LABELS[finding.verdict],
        },
        sourceRef: ref("comparison"),
      });
    }
    return annotations;
  });
}
