"use client";

import { useMemo } from "react";
import { FileText, Link2 } from "lucide-react";
import { TracePanelHeader, TracePanelSection } from "@/components/document-trace-panel";
import type { ScoutResponse } from "@/lib/api";
import {
  buildScoutDocumentAnnotations,
  type ScoutDocumentAnnotation,
  type ScoutDocumentTraceKind,
} from "@/lib/scout-document-trace";
import {
  DocumentTraceViewer,
} from "@/components/document-trace-viewer";
import type { DocumentTraceConnection } from "@/lib/document-trace";

const TRACE_LAYERS: Array<{
  value: ScoutDocumentTraceKind;
  label: string;
}> = [
  { value: "field", label: "Document fields" },
  { value: "quantitative_target", label: "Measurable targets" },
  { value: "relationship", label: "Evidence relationships" },
  { value: "grounding", label: "Evidence grounding" },
  { value: "calibration", label: "Quantitative calibration" },
  { value: "precedent", label: "Development precedent" },
];

function ScoutTraceInspector({
  annotation,
  connection,
}: {
  annotation: ScoutDocumentAnnotation;
  connection: DocumentTraceConnection;
}) {
  const connectionLabel = connection.type === "exact"
    ? "Exact source passage"
    : connection.type === "unavailable"
      ? "Unavailable source connection"
      : connection.markerReason === "quote_unmatched"
        ? "Unmatched source passage"
        : "Source passage connection";
  const unavailableBlockIds = new Set(connection.unavailableBlockIds ?? []);
  const hasRetainedCitation = annotation.blockIds.some((blockId) => !unavailableBlockIds.has(blockId));

  return (
    <div>
      <TracePanelHeader
        eyebrow={annotation.layerLabel}
        title={annotation.title}
        description="Saved result connected to the selected source passage."
      />

      <div className="px-5 py-5">
        {annotation.statusLabel && (
          <div className="inline-flex min-h-7 items-center rounded-full border border-border/80 bg-muted/25 px-2.5 text-[10px] font-medium text-foreground/80">
            {annotation.statusLabel}
          </div>
        )}

        <p className={annotation.statusLabel
          ? "mt-4 whitespace-pre-wrap text-sm leading-6 text-foreground/85"
          : "whitespace-pre-wrap text-sm leading-6 text-foreground/85"}
        >
          {annotation.summary}
        </p>

        <TracePanelSection
          label={connectionLabel}
          icon={connection.type === "exact" ? FileText : Link2}
          className="mt-5"
        >
          <p className="mt-2 text-xs leading-5 text-muted-foreground">
            {connection.type === "exact"
              ? "The highlight reproduces exact text retained in the saved result."
              : connection.type === "unavailable"
                ? `${unavailableBlockIds.size} cited ${unavailableBlockIds.size === 1 ? "passage is" : "passages are"} unavailable in the reconstructed document.${hasRetainedCitation ? " Other retained citations remain visible." : ""}`
                : connection.markerReason === "quote_unmatched"
                  ? "A saved exact passage cites this source passage but does not match its retained text literally. The trace does not substitute approximate text."
                  : "The saved result cites this source passage but does not claim an exact quotation for it."}
          </p>
          {connection.markerReason === "quote_unmatched" && connection.unmatchedQuotes?.length ? (
            <p className="mt-2 text-[10px] tabular-nums text-muted-foreground/80">
              {connection.unmatchedQuotes.length} unmatched exact {connection.unmatchedQuotes.length === 1 ? "passage" : "passages"}
            </p>
          ) : null}
          <p className="mt-2 text-[10px] tabular-nums text-muted-foreground/80">
            {annotation.blockIds.length} {annotation.blockIds.length === 1 ? "source passage" : "source passages"}
          </p>
        </TracePanelSection>
      </div>
    </div>
  );
}

export function ScoutDocumentTrace({
  result,
  focusBlockId,
  onFocusBlockConsumed,
}: {
  result: ScoutResponse;
  focusBlockId?: string | null;
  onFocusBlockConsumed?: (blockId: string) => void;
}) {
  const annotations = useMemo(
    () => buildScoutDocumentAnnotations(result),
    [result],
  );

  return (
    <DocumentTraceViewer
      blocks={result.blocks ?? []}
      annotations={annotations}
      layers={TRACE_LAYERS}
      focusBlockId={focusBlockId}
      onFocusBlockConsumed={onFocusBlockConsumed}
      renderInspector={(annotation, connection) => (
        <ScoutTraceInspector annotation={annotation} connection={connection} />
      )}
    />
  );
}
