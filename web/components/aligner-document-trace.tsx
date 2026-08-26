"use client";

import type { TraceFocus } from "@/lib/trace-focus";
import { useMemo } from "react";
import { CircleDashed, FileText, HelpCircle, Link2, Target } from "lucide-react";

import {
  DocumentTraceViewer,
  type DocumentTracePassageAccess,
} from "@/components/document-trace-viewer";
import {
  TracePanelHeader,
  TracePanelSection,
  TracePassageList,
} from "@/components/document-trace-panel";
import { ALIGNMENT_VERDICTS, VERDICT_LABELS, type AlignmentResult } from "@/lib/api";
import type { DocumentTraceConnection } from "@/lib/document-trace";
import {
  buildAlignerDocumentAnnotations,
  type AlignerDocumentAnnotation,
  type AlignerDocumentTraceKind,
} from "@/lib/aligner-document-trace";

/**
 * The inverse of the panels: which passages set a bar, and which passages answered one.
 *
 * The layers are the two sides of a comparison. `Requirement` shows where the bars are
 * stated in the reference document; the verdict layers show what the measured document
 * says about them. A reader following a shortfall wants the second; a reader asking
 * "what are we even holding them to" wants the first.
 *
 * Generated from the published verdict vocabulary rather than listed here, so adding a
 * verdict upstream gets a layer without this file changing.
 */
const TRACE_LAYERS: Array<{ value: AlignerDocumentTraceKind; label: string }> = [
  { value: "requirement", label: "Requirements" },
  ...ALIGNMENT_VERDICTS.map((verdict) => ({
    value: verdict,
    label: VERDICT_LABELS[verdict],
  })),
];

function AlignerTraceInspector({
  annotation,
  connection,
  passages,
}: {
  annotation: AlignerDocumentAnnotation;
  connection: DocumentTraceConnection;
  passages: DocumentTracePassageAccess;
}) {
  const ref = annotation.sourceRef;
  const isRequirement = ref.side === "reference";

  return (
    <div>
      <TracePanelHeader
        eyebrow={isRequirement ? "Requirement" : VERDICT_LABELS[ref.verdict]}
        title={ref.comparison}
        description={ref.requirementId}
      />

      <div className="px-5 py-5">
        <TracePanelSection label="The comparison asks" icon={HelpCircle}>
          <p className="mt-2 text-xs leading-5 text-muted-foreground">{ref.question}</p>
        </TracePanelSection>

        <TracePanelSection label="The requirement" icon={Target} className="mt-5">
          <p className="mt-2 text-xs leading-5 text-muted-foreground">
            {ref.requirement}
          </p>
        </TracePanelSection>

        {!isRequirement && (
          <p className="mt-5 whitespace-pre-wrap text-sm leading-6 text-foreground/85">
            {ref.statement}
          </p>
        )}

        {ref.gap && !isRequirement && (
          <TracePanelSection label="Still to close" icon={CircleDashed} className="mt-5">
            <p className="mt-2 text-xs leading-5 text-muted-foreground">{ref.gap}</p>
          </TracePanelSection>
        )}

        <TracePanelSection
          label={isRequirement ? "Where the bar is stated" : "Source passages"}
          icon={connection.type === "exact" ? FileText : Link2}
          className="mt-5"
        >
          <p className="mt-2 text-xs leading-5 text-muted-foreground">
            {isRequirement
              ? "The requirement was read from every passage listed below, in the document that sets it. The verdict against it is marked in the other document."
              : "This verdict was read from every passage listed below. Aligner records block lineage rather than exact quotations, so the whole passage is marked rather than a span within it."}
          </p>
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

export function AlignerDocumentTrace({
  result,
  focus,
  onFocusConsumed,
}: {
  result: AlignmentResult;
  focus?: TraceFocus | null;
  onFocusConsumed?: (focus: TraceFocus) => void;
}) {
  const annotations = useMemo(
    () => buildAlignerDocumentAnnotations(result),
    [result],
  );

  return (
    <DocumentTraceViewer
      blocks={result.blocks}
      annotations={annotations}
      layers={TRACE_LAYERS}
      // Shortfalls first: they are the ones a reader can act on, and the reason a PPL
      // opened the trace at all.
      defaultLayer="falls_short"
      focus={focus}
      onFocusConsumed={onFocusConsumed}
      renderInspector={(annotation, connection, passages) => (
        <AlignerTraceInspector
          annotation={annotation}
          connection={connection}
          passages={passages}
        />
      )}
    />
  );
}
