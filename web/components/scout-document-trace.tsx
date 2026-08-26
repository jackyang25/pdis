"use client";

import type { TraceFocus } from "@/lib/trace-focus";
import { useMemo } from "react";
import { FileText, Link2 } from "lucide-react";
import {
  TracePanelHeader,
  TracePanelSection,
  TracePassageList,
} from "@/components/document-trace-panel";
import type { ScoutResponse } from "@/lib/api";
import {
  buildScoutDocumentAnnotations,
  type ScoutDocumentAnnotation,
  type ScoutDocumentTraceKind,
} from "@/lib/scout-document-trace";
import {
  DocumentTraceViewer,
  type DocumentTracePassageAccess,
} from "@/components/document-trace-viewer";
import type { DocumentTraceConnection } from "@/lib/document-trace";
import { Quoted, Reading } from "@/components/ui/evidence-text";
import { VerdictPill } from "@/components/ui/verdict-pill";
import { cn } from "@/lib/utils";

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
  passages,
}: {
  annotation: ScoutDocumentAnnotation;
  connection: DocumentTraceConnection;
  passages: DocumentTracePassageAccess;
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
        {/* Tinted by the annotation's own tone, which was already on it and thrown
            away: the pill was a fixed neutral grey, so the same verdict read as tinted
            in a list and as unremarkable in the panel that explains it. */}
        {annotation.statusLabel && (
          <VerdictPill
            label={annotation.statusLabel}
            tone={annotation.emphasis?.tone ?? "neutral"}
          />
        )}

        {/* Two of Scout's six annotation kinds summarise with the document's own words -
            a field's stated target, and the passage a measurable target was read from.
            Rendered as a model's they carried the authorship mark, which is the tool
            claiming it wrote the reader's document. */}
        {annotation.summaryMode === "quoted" ? (
          <Quoted size="prominent" className={cn(annotation.statusLabel && "mt-4")}>
            {annotation.summary}
          </Quoted>
        ) : (
          <Reading
            size="body"
            className={cn(
              "whitespace-pre-wrap",
              annotation.statusLabel && "mt-4",
            )}
          >
            {annotation.summary}
          </Reading>
        )}

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
          <TracePassageList
            passages={passages.passages}
            openedBlockId={connection.blockId}
            onReveal={passages.reveal}
          />
        </TracePanelSection>
      </div>
    </div>
  );
}

export function ScoutDocumentTrace({
  result,
  focus,
  onFocusConsumed,
}: {
  result: ScoutResponse;
  focus?: TraceFocus | null;
  onFocusConsumed?: (focus: TraceFocus) => void;
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
      focus={focus}
      onFocusConsumed={onFocusConsumed}
      renderInspector={(annotation, connection, passages) => (
        <ScoutTraceInspector
          annotation={annotation}
          connection={connection}
          passages={passages}
        />
      )}
    />
  );
}
