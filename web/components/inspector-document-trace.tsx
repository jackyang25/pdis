"use client";

import { useMemo } from "react";
import { CircleDashed, FileText, Link2, ListChecks, Wrench } from "lucide-react";

import { DocumentTraceViewer } from "@/components/document-trace-viewer";
import { TracePanelHeader, TracePanelSection } from "@/components/document-trace-panel";
import type { InspectionResult } from "@/lib/api";
import type { DocumentTraceConnection } from "@/lib/document-trace";
import {
  buildInspectorDocumentAnnotations,
  type InspectorDocumentAnnotation,
  type InspectorDocumentTraceKind,
} from "@/lib/inspector-document-trace";

/**
 * Inspector's four layers are its own result axes, which `AGENTS.md` guarantees
 * are independent. Severity is deliberately not a layer: the layer chooses which
 * question is being asked, and the block tone answers how bad the answer is, so
 * triage stays visible inside every layer.
 */
const TRACE_LAYERS: Array<{ value: InspectorDocumentTraceKind; label: string }> = [
  { value: "completeness", label: "Completeness" },
  { value: "adherence", label: "Template adherence" },
  { value: "rigor", label: "Rigor" },
  { value: "consistency", label: "Cross-section consistency" },
];

function InspectorTraceInspector({
  annotation,
  connection,
}: {
  annotation: InspectorDocumentAnnotation;
  connection: DocumentTraceConnection;
}) {
  const ref = annotation.sourceRef;
  const absent = annotation.blockIds.length === 0;

  const issues = ref.type === "consistency" ? [] : ref.issues;
  const recommendation = ref.recommendation;

  return (
    <div>
      <TracePanelHeader
        eyebrow={annotation.layerLabel}
        title={annotation.title}
        description={
          ref.type === "consistency"
            ? "Two sections that cannot both hold as written."
            : ref.type === "section"
              ? `Section-level judgment · ${ref.sectionName}`
              : `${ref.sectionName} · rubric variable`
        }
      />

      <div className="px-5 py-5">
        {annotation.statusLabel && (
          <div className="inline-flex min-h-7 items-center rounded-full border border-border/80 bg-muted/25 px-2.5 text-[10px] font-medium text-foreground/80">
            {annotation.statusLabel}
          </div>
        )}

        <p className="mt-4 whitespace-pre-wrap text-sm leading-6 text-foreground/85">
          {annotation.summary}
        </p>

        {issues.length > 0 && (
          <TracePanelSection label="Issues" icon={ListChecks} className="mt-5">
            <ul className="mt-2 space-y-1.5">
              {issues.map((issue, index) => (
                <li
                  key={`${annotation.id}:issue:${index}`}
                  className="text-xs leading-5 text-muted-foreground"
                >
                  {issue}
                </li>
              ))}
            </ul>
          </TracePanelSection>
        )}

        {recommendation && (
          <TracePanelSection label="Recommendation" icon={Wrench} className="mt-5">
            <p className="mt-2 text-xs leading-5 text-muted-foreground">{recommendation}</p>
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
              : "The grade applies to every retained passage cited below. Inspector records block lineage rather than exact quotations, so the whole passage is marked rather than a span within it."}
          </p>
          {!absent && (
            <p className="mt-2 text-[10px] tabular-nums text-muted-foreground/80">
              {annotation.blockIds.length}{" "}
              {annotation.blockIds.length === 1 ? "source passage" : "source passages"}
            </p>
          )}
        </TracePanelSection>

        {ref.type === "consistency" && ref.sections.length > 0 && (
          <TracePanelSection label="Sections in conflict" className="mt-5">
            <ul className="mt-2 space-y-1">
              {ref.sections.map((section) => (
                <li key={section} className="text-xs leading-5 text-muted-foreground">
                  {section}
                </li>
              ))}
            </ul>
          </TracePanelSection>
        )}
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
      // Grades are per-dimension, so the view opens on one. Completeness first:
      // whether required content exists is the question that gates the others.
      defaultLayer="completeness"
      focusBlockId={focusBlockId}
      onFocusBlockConsumed={onFocusBlockConsumed}
      renderInspector={(annotation, connection) => (
        <InspectorTraceInspector annotation={annotation} connection={connection} />
      )}
    />
  );
}
