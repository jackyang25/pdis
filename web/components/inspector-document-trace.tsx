"use client";

import { useMemo } from "react";
import { CircleDashed, FileText, Link2, Wrench } from "lucide-react";

import { DocumentTraceViewer } from "@/components/document-trace-viewer";
import { TracePanelHeader, TracePanelSection } from "@/components/document-trace-panel";
import { FINDING_REASONS, REASON_LABELS, STATUS_LABELS } from "@/lib/api";
import type { InspectionResult } from "@/lib/api";
import type { DocumentTraceConnection } from "@/lib/document-trace";
import {
  buildInspectorDocumentAnnotations,
  type InspectorDocumentAnnotation,
  type InspectorDocumentTraceKind,
} from "@/lib/inspector-document-trace";

/**
 * The layers are the reasons a finding can exist, generated from the published
 * vocabulary rather than listed here. A reason added upstream gets a layer without
 * this file changing; it was previously a hand-kept list of the internal question
 * names, which is the coupling that made adding a question a change at every layer.
 *
 * The level is deliberately not a layer: the layer chooses which kind of problem to
 * look at, and the block tone answers how much it blocks, so triage stays visible
 * inside every layer.
 */
const TRACE_LAYERS: Array<{ value: InspectorDocumentTraceKind; label: string }> =
  FINDING_REASONS.map((reason) => ({ value: reason, label: REASON_LABELS[reason] }));

function InspectorTraceInspector({
  annotation,
  connection,
}: {
  annotation: InspectorDocumentAnnotation;
  connection: DocumentTraceConnection;
}) {
  const ref = annotation.sourceRef;
  const absent = annotation.blockIds.length === 0;
  const where = ref.variableName
    ? `${ref.variableName} · ${ref.sectionName}`
    : ref.sectionName
      ? `The ${ref.sectionName} section as a whole`
      : "Spans more than one section";

  return (
    <div>
      <TracePanelHeader
        eyebrow={annotation.layerLabel}
        title={annotation.title}
        description={where}
      />

      <div className="px-5 py-5">
        {ref.status && (
          <span
            title={STATUS_LABELS[ref.status]}
            className="inline-flex min-h-7 items-center rounded-full border border-border/80 bg-muted/25 px-2.5 text-[10px] font-medium text-foreground/80"
          >
            {STATUS_LABELS[ref.status]}
          </span>
        )}

        <p className="mt-4 whitespace-pre-wrap text-sm leading-6 text-foreground/85">
          {annotation.summary}
        </p>

        {ref.recommendation && (
          <TracePanelSection label="Recommendation" icon={Wrench} className="mt-5">
            <p className="mt-2 text-xs leading-5 text-muted-foreground">
              {ref.recommendation}
            </p>
          </TracePanelSection>
        )}

        <TracePanelSection
          label={absent ? "Not present in the document" : "Source passages"}
          icon={absent ? CircleDashed : connection.type === "exact" ? FileText : Link2}
          className="mt-5"
        >
          <p className="mt-2 text-xs leading-5 text-muted-foreground">
            {absent
              ? "This finding describes content that is absent, so it cites no source passage. It is shown beside the section it belongs to rather than attached to unrelated text."
              : "This finding was read from every passage cited below. Inspector records block lineage rather than exact quotations, so the whole passage is marked rather than a span within it."}
          </p>
          {!absent && (
            <p className="mt-2 text-[10px] tabular-nums text-muted-foreground/80">
              {annotation.blockIds.length}{" "}
              {annotation.blockIds.length === 1 ? "source passage" : "source passages"}
            </p>
          )}
        </TracePanelSection>
      </div>
    </div>
  );
}

export function InspectorDocumentTrace({
  result,
  focusBlockId,
  onFocusBlockConsumed,
}: {
  result: InspectionResult;
  focusBlockId?: string | null;
  onFocusBlockConsumed?: (blockId: string) => void;
}) {
  const annotations = useMemo(
    () => buildInspectorDocumentAnnotations(result),
    [result],
  );

  return (
    <DocumentTraceViewer
      blocks={result.blocks ?? []}
      annotations={annotations}
      layers={TRACE_LAYERS}
      // Absence first: whether the rubric's content exists at all is the question
      // that gates the others.
      defaultLayer="missing"
      focusBlockId={focusBlockId}
      onFocusBlockConsumed={onFocusBlockConsumed}
      renderInspector={(annotation, connection) => (
        <InspectorTraceInspector annotation={annotation} connection={connection} />
      )}
    />
  );
}
