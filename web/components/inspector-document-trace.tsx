"use client";

import type { TraceFocus } from "@/lib/trace-focus";
import { useMemo } from "react";
import { CircleDashed, FileText, Link2 } from "lucide-react";

import {
  DocumentTraceViewer,
  type DocumentTracePassageAccess,
} from "@/components/document-trace-viewer";
import {
  TracePanelHeader,
  TracePanelSection,
  TracePassageList,
} from "@/components/document-trace-panel";
import { ASSESSED_VERDICTS, VERDICT_DESCRIPTION, VERDICT_LABEL } from "@/lib/api";
import type { InspectionResult } from "@/lib/api";
import type { DocumentTraceConnection } from "@/lib/document-trace";
import { Reading } from "@/components/ui/evidence-text";
import {
  buildInspectorDocumentAnnotations,
  type InspectorDocumentAnnotation,
  type InspectorDocumentTraceKind,
} from "@/lib/inspector-document-trace";

/**
 * The layers are the verdicts that name something to fix, generated from the
 * published vocabulary rather than listed here. A verdict added upstream gets a layer
 * without this file changing; it was previously a hand-kept list of the internal
 * question names, which is the coupling that made adding a question a change at every
 * layer.
 *
 * `specified` and `not_applicable` are not layers: the trace marks what needs work,
 * and a layer holding every sound unit would mark most of the document.
 */
const TRACE_LAYERS: Array<{ value: InspectorDocumentTraceKind; label: string }> =
  ASSESSED_VERDICTS.map((verdict) => ({ value: verdict, label: VERDICT_LABEL[verdict] }));

function InspectorTraceInspector({
  annotation,
  connection,
  passages,
}: {
  annotation: InspectorDocumentAnnotation;
  connection: DocumentTraceConnection;
  passages: DocumentTracePassageAccess;
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
        {/* One pill, because there is one axis. It used to show a unit status here
            beside a reason in the eyebrow above - two words for one judgement, and a
            reader had no way to know they were the same field. */}
        <span
          title={VERDICT_DESCRIPTION[ref.verdict]}
          className="inline-flex min-h-7 items-center rounded-full border border-border/80 bg-foreground/[0.045] px-2.5 text-[10px] font-medium text-foreground/80"
        >
          {/* The short form. This rendered the description, which is a sentence, as pill
              text: "The rubric asks for this and the document does not usably supply it". */}
          {VERDICT_LABEL[ref.verdict]}
        </span>

        <Reading size="body" className="mt-4 whitespace-pre-wrap">
          {annotation.summary}
        </Reading>

        <TracePanelSection
          label={absent ? "Not present in the document" : "Source passages"}
          icon={absent ? CircleDashed : connection.type === "exact" ? FileText : Link2}
          className="mt-5"
        >
          <p className="mt-2 text-xs leading-5 text-muted-foreground">
            {absent
              ? "This finding describes content that is absent, so it cites no source passage. It is shown beside the section it belongs to rather than attached to unrelated text."
              : "This finding was read from every passage listed below. Inspector records block lineage rather than exact quotations, so the whole passage is marked rather than a span within it."}
          </p>
          {!absent && (
            <TracePassageList
              passages={passages.passages}
              openedBlockId={connection.blockId}
              onReveal={passages.reveal}
            />
          )}
        </TracePanelSection>
      </div>
    </div>
  );
}

export function InspectorDocumentTrace({
  result,
  focus,
  onFocusConsumed,
}: {
  result: InspectionResult;
  focus?: TraceFocus | null;
  onFocusConsumed?: (focus: TraceFocus) => void;
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
      defaultLayer="not_present"
      focus={focus}
      onFocusConsumed={onFocusConsumed}
      renderInspector={(annotation, connection, passages) => (
        <InspectorTraceInspector
          annotation={annotation}
          connection={connection}
          passages={passages}
        />
      )}
    />
  );
}
