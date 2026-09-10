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
  TracePanelBody,
  TraceBlockCitationNote,
  TracePanelSection,
  TracePassageList,
} from "@/components/document-trace-panel";
import { ASSESSED_VERDICTS, VERDICT_DESCRIPTION, VERDICT_LABEL } from "@/lib/api";
import type { InspectionReviewView } from "@/lib/api";
import { InspectorRequirement } from "@/components/inspector-rubric-details";
import type { DocumentTraceConnection } from "@/lib/document-trace";
import { Reading } from "@/components/ui/evidence-text";
import { VerdictPill } from "@/components/ui/verdict-pill";
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
  result,
}: {
  annotation: InspectorDocumentAnnotation;
  connection: DocumentTraceConnection;
  passages: DocumentTracePassageAccess;
  result: InspectionReviewView;
}) {
  const ref = annotation.sourceRef;
  const absent = annotation.blockIds.length === 0;
  const requirement = result.rubric.requirements.find(item => item.id === ref.assessmentId);
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
        description={`${ref.verdict === "section_conflict" ? "Document consistency" : result.rubric.display_name} · ${where}`}
      />

      <TracePanelBody>
        {/* One pill, because there is one axis. It used to show a unit status here
            beside a reason in the eyebrow above - two words for one judgement, and a
            reader had no way to know they were the same field. */}
        {/* The short form, tinted by the annotation's own tone. It rendered the
            description here once - a whole sentence as pill text - and then a fixed
            neutral grey, which discarded a tone the annotation already carried. */}
        <VerdictPill
          label={VERDICT_LABEL[ref.verdict]}
          tone={annotation.emphasis?.tone ?? "neutral"}
          description={VERDICT_DESCRIPTION[ref.verdict]}
        />

        <Reading size="body" className="whitespace-pre-wrap">
          {annotation.summary}
        </Reading>
        {requirement && <InspectorRequirement requirement={requirement} rubric={result.rubric} />}

        <TracePanelSection
          label={absent ? "Not present in the document" : "Source passages"}
          icon={absent ? CircleDashed : connection.type === "exact" ? FileText : Link2}
        >
          {absent ? (
            <p className="mt-2 text-xs leading-5 text-muted-foreground">
              This finding describes content that is absent, so it cites no source passage. It is shown beside the section it belongs to rather than attached to unrelated text.
            </p>
          ) : <TraceBlockCitationNote />}
          {!absent && (
            <TracePassageList
              passages={passages.passages}
              openedBlockId={connection.blockId}
              onReveal={passages.reveal}
            />
          )}
        </TracePanelSection>
      </TracePanelBody>
    </div>
  );
}

export function InspectorDocumentTrace({
  result,
  focus,
  onFocusConsumed,
}: {
  result: InspectionReviewView;
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
          result={result}
        />
      )}
    />
  );
}
