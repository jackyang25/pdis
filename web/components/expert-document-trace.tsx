"use client";

import { useMemo } from "react";
import { FileText, HelpCircle, Link2 } from "lucide-react";

import { DocumentTraceViewer } from "@/components/document-trace-viewer";
import { TracePanelHeader, TracePanelSection } from "@/components/document-trace-panel";
import type { GateReview } from "@/lib/api";
import type { DocumentTraceConnection } from "@/lib/document-trace";
import {
  buildExpertDocumentAnnotations,
  type ExpertDocumentAnnotation,
  type ExpertDocumentTraceKind,
} from "@/lib/expert-document-trace";

/**
 * The inverse of the panels: which passages carried an answer, and what they answered.
 *
 * One tab, not one per document. `DocumentTraceViewer` already switches between the
 * documents a result carries, so per-document tabs would be a second mechanism for the
 * same thing — and one that breaks when a run holds a single document.
 *
 * One layer, because Expert's citations are all the same claim. Inspector filters by
 * finding reason and Scout by evidence axis; a filter here would have nothing to
 * separate, so the selector stays out of the way rather than offering a choice of one.
 */
const TRACE_LAYERS: Array<{ value: ExpertDocumentTraceKind; label: string }> = [
  { value: "answered", label: "Answered" },
];

function ExpertTraceInspector({
  annotation,
  connection,
}: {
  annotation: ExpertDocumentAnnotation;
  connection: DocumentTraceConnection;
}) {
  const ref = annotation.sourceRef;
  return (
    <div>
      <TracePanelHeader
        eyebrow={ref.pq ? "Answered · WHO prequalification" : annotation.layerLabel}
        title={ref.discipline}
        description={ref.questionId}
      />

      <div className="px-5 py-5">
        <TracePanelSection label="The question" icon={HelpCircle}>
          <p className="mt-2 text-xs leading-5 text-muted-foreground">{ref.question}</p>
        </TracePanelSection>

        <p className="mt-5 whitespace-pre-wrap text-sm leading-6 text-foreground/85">
          {annotation.summary}
        </p>

        <TracePanelSection
          label="Source passages"
          icon={connection.type === "exact" ? FileText : Link2}
          className="mt-5"
        >
          <p className="mt-2 text-xs leading-5 text-muted-foreground">
            This answer was read from every passage marked below. Expert records block
            lineage rather than exact quotations, so the whole passage is marked rather
            than a span within it.
          </p>
          <p className="mt-2 text-[10px] tabular-nums text-muted-foreground/80">
            {annotation.blockIds.length}{" "}
            {annotation.blockIds.length === 1 ? "source passage" : "source passages"}
          </p>
        </TracePanelSection>
      </div>
    </div>
  );
}

export function ExpertDocumentTrace({
  review,
  focusBlockId,
  onFocusBlockConsumed,
}: {
  review: GateReview;
  focusBlockId?: string | null;
  onFocusBlockConsumed?: (blockId: string) => void;
}) {
  const annotations = useMemo(
    () => buildExpertDocumentAnnotations(review),
    [review],
  );

  return (
    <DocumentTraceViewer
      blocks={review.blocks ?? []}
      annotations={annotations}
      layers={TRACE_LAYERS}
      defaultLayer="answered"
      focusBlockId={focusBlockId}
      onFocusBlockConsumed={onFocusBlockConsumed}
      renderInspector={(annotation, connection) => (
        <ExpertTraceInspector annotation={annotation} connection={connection} />
      )}
    />
  );
}
