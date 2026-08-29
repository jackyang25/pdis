import type {
  EvidenceAssessment,
  Match,
  PrecedentSignal,
  ScoutResponse,
} from "./api.ts";
import { stableHash } from "./utils.ts";
import {
  displayAttributeLabel,
  RELATIONSHIP_LABEL,
  GROUNDING_LABEL,
  PRECEDENT_LABEL,
  OUTCOME_LABEL,
} from "./scout-labels.ts";
import type { DocumentAnnotation } from "./document-trace.ts";
import { traceSpans } from "./document-trace.ts";

export type ScoutDocumentTraceKind =
  | "field"
  | "quantitative_target"
  | "relationship"
  | "grounding"
  | "calibration"
  | "precedent";

export type ScoutDocumentTraceRef =
  | { type: "field"; attributeRef: string }
  | { type: "quantitative_target"; targetId: string; attributeRefs: string[] }
  | { type: "relationship"; insightId: string; attributeRef: string }
  | { type: "grounding"; attributeRef: string }
  | { type: "calibration"; targetId: string; attributeRefs: string[] }
  | { type: "precedent"; attributeRef: string };

export type ScoutDocumentAnnotation = DocumentAnnotation<
  ScoutDocumentTraceKind,
  ScoutDocumentTraceRef
>;






function unique(values: Array<string | null | undefined>): string[] {
  return values
    .map((value) => value?.trim() ?? "")
    .filter((value, index, items) => Boolean(value) && items.indexOf(value) === index);
}

function annotationId(prefix: string, values: Array<string | null | undefined>): string {
  return `${prefix}:${stableHash(values.map((value) => value ?? "").join("\u241f"))}`;
}

function hasLineage(blockIds: string[]): boolean {
  return blockIds.length > 0;
}

export function buildScoutDocumentAnnotations(
  result: ScoutResponse,
): ScoutDocumentAnnotation[] {
  const annotations: ScoutDocumentAnnotation[] = [];

  for (const variable of result.variables ?? []) {
    const blockIds = unique([
      ...(variable.block_ids ?? []),
      ...variable.document_spans.flatMap((span) => span.block_ids),
    ]);
    if (!hasLineage(blockIds)) continue;
    annotations.push({
      id: `field:${variable.name}`,
      kind: "field",
      layerLabel: "Document field",
      title: displayAttributeLabel(variable.name),
      summary: variable.document_target,
      // The document's own target text, copied. Not a model's sentence about it.
      summaryMode: "quoted",
      statusLabel: variable.target_resolved ? "Resolved" : "Unresolved",
      blockIds,
      spans: traceSpans(variable.document_spans),
      sourceRef: { type: "field", attributeRef: variable.name },
    });
  }

  for (const target of result.quantitative_ledger?.targets ?? []) {
    const attributeRefs = unique(target.field_links.map((link) => link.attribute_ref));
    const blockIds = unique([
      ...target.doc_block_ids,
      ...target.provenance_spans.flatMap((span) => span.block_ids),
    ]);
    if (!hasLineage(blockIds)) continue;
    annotations.push({
      id: `quantitative-target:${target.id}`,
      kind: "quantitative_target",
      layerLabel: "Measurable target",
      title: attributeRefs.length
        ? attributeRefs.map(displayAttributeLabel).join(" · ")
        : target.id,
      summary: target.quote,
      // The passage the target was read from, verbatim.
      summaryMode: "quoted",
      statusLabel: target.review_status === "approved"
        ? "Approved"
        : target.review_status === "rejected"
          ? "Rejected"
          : "Needs review",
      blockIds,
      spans: traceSpans(target.provenance_spans),
      sourceRef: { type: "quantitative_target", targetId: target.id, attributeRefs },
    });
  }

  for (const match of result.matches ?? []) {
    const blockIds = unique(match.doc_block_ids ?? []);
    const attributeRef = match.insight.attribute_ref ?? "";
    if (!attributeRef || !hasLineage(blockIds)) continue;
    const insightId = match.insight.id ?? annotationId("insight", [
      attributeRef,
      match.insight.statement,
      match.insight.query,
    ]);
    annotations.push({
      id: annotationId("relationship", [insightId, match.relation, match.reason, ...blockIds]),
      kind: "relationship",
      layerLabel: "Evidence relationship",
      title: displayAttributeLabel(attributeRef),
      summary: match.reason,
      statusLabel: RELATIONSHIP_LABEL[match.relation],
      blockIds,
      spans: [],
      sourceRef: { type: "relationship", insightId, attributeRef },
    });
  }

  for (const assessment of result.assessments ?? []) {
    const blockIds = unique(assessment.doc_block_ids);
    if (!hasLineage(blockIds)) continue;
    annotations.push({
      id: `grounding:${assessment.attribute_ref}`,
      kind: "grounding",
      layerLabel: "Evidence grounding",
      title: displayAttributeLabel(assessment.attribute_ref),
      summary: assessment.reason,
      statusLabel: GROUNDING_LABEL[assessment.strength],
      blockIds,
      spans: [],
      sourceRef: { type: "grounding", attributeRef: assessment.attribute_ref },
    });
  }

  for (const score of result.conformity ?? []) {
    const blockIds = unique(score.doc_block_ids ?? []);
    if (!hasLineage(blockIds)) continue;
    const attributeRefs = unique(score.attribute_refs);
    annotations.push({
      id: `calibration:${score.target_id}`,
      kind: "calibration",
      layerLabel: "Quantitative calibration",
      title: attributeRefs.length
        ? attributeRefs.map(displayAttributeLabel).join(" · ")
        : score.target_label,
      summary: score.verdict,
      statusLabel: score.calibration_status === "insufficient"
        ? "Insufficient basis"
        : score.calibration_status === "limited"
          ? "Limited basis"
          : "Sufficient basis",
      blockIds,
      spans: [],
      sourceRef: { type: "calibration", targetId: score.target_id, attributeRefs },
    });
  }

  for (const signal of result.precedents ?? []) {
    const blockIds = unique(signal.doc_block_ids);
    if (!hasLineage(blockIds)) continue;
    annotations.push({
      id: `precedent:${signal.attribute_ref}`,
      kind: "precedent",
      layerLabel: "Development precedent",
      title: displayAttributeLabel(signal.attribute_ref),
      summary: signal.reason,
      statusLabel: `${PRECEDENT_LABEL[signal.precedent]} · ${OUTCOME_LABEL[signal.outcome]}`,
      blockIds,
      spans: [],
      sourceRef: { type: "precedent", attributeRef: signal.attribute_ref },
    });
  }

  return annotations;
}
