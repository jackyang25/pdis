"use client";

import {
  type ReactNode,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { FileText, Layers3, Link2, X } from "lucide-react";
import { BlockReferenceId } from "@/components/block-reference";
import { TracePanelHeader } from "@/components/document-trace-panel";
import type { ContentBlock } from "@/lib/api";
import {
  documentBlockPresentation,
  documentBlockSpacing,
  documentTableCells,
  type DocumentBlockSpacing,
  documentTraceRailMode,
} from "@/lib/document-block-presentation";
import {
  buildDocumentTrace,
  documentTraceFocusTarget,
  documentTraceSegmentsInRange,
  filterDocumentAnnotations,
  groupDocumentTraceMarkers,
  type DocumentAnnotation,
  type DocumentTraceConnection,
  type DocumentTraceBlock,
  type DocumentTraceSegment,
} from "@/lib/document-trace";
import { cn } from "@/lib/utils";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

type LayerOption<TKind extends string> = {
  value: TKind;
  label: string;
};

export type DocumentTraceViewerProps<TKind extends string, TRef> = {
  blocks: ContentBlock[];
  annotations: Array<DocumentAnnotation<TKind, TRef>>;
  layers: Array<LayerOption<TKind>>;
  renderInspector: (
    annotation: DocumentAnnotation<TKind, TRef>,
    connection: DocumentTraceConnection,
  ) => ReactNode;
  focusBlockId?: string | null;
  onFocusBlockConsumed?: (blockId: string) => void;
};

function displayDocumentName(docId: string): string {
  return docId.replace(/[-_]+/g, " ").replace(/\s+/g, " ").trim() || "Source document";
}

function annotationButtonLabel<TKind extends string, TRef>(
  annotations: Array<DocumentAnnotation<TKind, TRef>>,
): string {
  if (annotations.length > 1) {
    return `View ${annotations.length} connected results: ${annotations
      .map((annotation) => `${annotation.layerLabel}, ${annotation.title}`)
      .join("; ")}`;
  }
  const annotation = annotations[0];
  return annotation
    ? `View ${annotation.layerLabel}: ${annotation.title}`
    : "View connected result";
}

function markerGroupLabel(
  reason: "block_only" | "quote_unmatched",
  count: number,
): string {
  if (reason === "quote_unmatched") {
    return `${count} unmatched ${count === 1 ? "excerpt" : "excerpts"}`;
  }
  return `${count} linked ${count === 1 ? "result" : "results"}`;
}

function blockSpacingClass(spacing: DocumentBlockSpacing): string {
  switch (spacing) {
    case "major":
      return "pt-10";
    case "section":
      return "pt-8";
    case "subsection":
      return "pt-6";
    case "body":
      return "pt-3";
    case "continuation":
      return "pt-0";
  }
}

function TraceSegmentText<TKind extends string, TRef>({
  blockId,
  segments,
  annotationsById,
  activeAnnotationIds,
  onSelect,
}: {
  blockId: string;
  segments: DocumentTraceSegment[];
  annotationsById: Map<string, DocumentAnnotation<TKind, TRef>>;
  activeAnnotationIds: string[];
  onSelect: (annotationIds: string[], trigger: HTMLElement, connection: DocumentTraceConnection) => void;
}) {
  return segments.map((segment, index) => {
    if (!segment.annotationIds.length) {
      return <span key={`${blockId}:text:${segment.start}:${segment.end}:${index}`}>{segment.text}</span>;
    }
    const segmentAnnotations = segment.annotationIds
      .map((id) => annotationsById.get(id))
      .filter((annotation): annotation is DocumentAnnotation<TKind, TRef> => Boolean(annotation));
    const isActive = segment.annotationIds.some((id) => activeAnnotationIds.includes(id));
    return (
      <button
        key={`${blockId}:annotation:${segment.start}:${segment.end}:${index}`}
        type="button"
        className={cn(
          "inline box-decoration-clone rounded-[3px] bg-amber-100/80 px-0.5 text-left text-inherit transition-colors hover:bg-amber-200/75 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500/35 dark:bg-amber-300/15 dark:hover:bg-amber-300/25 motion-reduce:transition-none",
          isActive && "bg-amber-200/90 ring-1 ring-amber-500/25 dark:bg-amber-300/30",
        )}
        aria-label={annotationButtonLabel(segmentAnnotations)}
        aria-pressed={isActive}
        onClick={(event) => onSelect(segment.annotationIds, event.currentTarget, {
          type: "exact",
          blockId,
        })}
      >
        {segment.text}
      </button>
    );
  });
}

function BlockText<TKind extends string, TRef>({
  traceBlock,
  annotationsById,
  activeAnnotationIds,
  onSelect,
}: {
  traceBlock: DocumentTraceBlock<TKind, TRef>;
  annotationsById: Map<string, DocumentAnnotation<TKind, TRef>>;
  activeAnnotationIds: string[];
  onSelect: (annotationIds: string[], trigger: HTMLElement, connection: DocumentTraceConnection) => void;
}) {
  const content = (
    <TraceSegmentText
      blockId={traceBlock.block.id}
      segments={traceBlock.segments}
      annotationsById={annotationsById}
      activeAnnotationIds={activeAnnotationIds}
      onSelect={onSelect}
    />
  );

  if (traceBlock.block.block_type === "image" && traceBlock.block.image) {
    const source = `data:${traceBlock.block.image.media_type};base64,${traceBlock.block.image.data_base64}`;
    return (
      <figure className="my-7">
        {/* The retained block text is the only available source-authored alternative text. */}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={source}
          alt={traceBlock.block.content.trim() ? "" : "Source document image"}
          className="mx-auto max-h-[34rem] max-w-full rounded-md object-contain outline outline-1 outline-black/10 dark:outline-white/10"
        />
        {traceBlock.block.content.trim() && (
          <figcaption className="mx-auto mt-2 max-w-2xl text-center text-xs leading-5 text-muted-foreground">
            {content}
          </figcaption>
        )}
      </figure>
    );
  }

  const presentation = documentBlockPresentation(traceBlock.block);

  if (presentation === "heading-primary") {
    return (
      <h2 className="m-0 text-balance font-display text-xl font-semibold leading-tight tracking-[-0.02em] text-foreground">
        {content}
      </h2>
    );
  }

  if (presentation === "heading-secondary") {
    return (
      <h3 className="m-0 text-balance font-display text-lg font-semibold leading-tight tracking-[-0.015em] text-foreground">
        {content}
      </h3>
    );
  }

  if (presentation === "heading-tertiary") {
    return (
      <h4 className="m-0 text-balance font-display text-[15px] font-semibold leading-snug text-foreground">
        {content}
      </h4>
    );
  }

  if (presentation === "table-row") {
    const tableRow = documentTableCells(traceBlock.block);
    if (tableRow) {
      return (
        <div className="overflow-x-auto py-1">
          <dl
            className="grid gap-x-5 gap-y-2 border-l border-border/70 pl-4"
            style={{
              gridTemplateColumns: `repeat(${tableRow.columnCount}, minmax(0, 1fr))`,
              minWidth: tableRow.columnCount > 3
                ? `${tableRow.columnCount * 9}rem`
                : undefined,
            }}
          >
            {tableRow.cells.map((cell) => {
              const headerSegments = documentTraceSegmentsInRange(
                traceBlock.segments,
                cell.contentStart,
                cell.valueStart,
              );
              const valueSegments = documentTraceSegmentsInRange(
                traceBlock.segments,
                cell.valueStart,
                cell.valueEnd,
              );
              return (
                <div
                  key={`${traceBlock.block.id}:cell:${cell.columnIndex}`}
                  className="min-w-0"
                  style={{ gridColumnStart: cell.columnIndex + 1 }}
                >
                  {headerSegments.length > 0 && (
                    <dt className="mb-1 text-[10px] font-semibold uppercase leading-4 tracking-[0.08em] text-muted-foreground">
                      <TraceSegmentText
                        blockId={traceBlock.block.id}
                        segments={headerSegments}
                        annotationsById={annotationsById}
                        activeAnnotationIds={activeAnnotationIds}
                        onSelect={onSelect}
                      />
                    </dt>
                  )}
                  <dd className="m-0 whitespace-pre-wrap text-[13px] leading-5 tabular-nums text-foreground/85">
                    <TraceSegmentText
                      blockId={traceBlock.block.id}
                      segments={valueSegments}
                      annotationsById={annotationsById}
                      activeAnnotationIds={activeAnnotationIds}
                      onSelect={onSelect}
                    />
                  </dd>
                </div>
              );
            })}
          </dl>
        </div>
      );
    }
    return (
      <p className="m-0 whitespace-pre-wrap bg-muted/20 px-3 py-2 text-[13px] leading-5 tabular-nums text-foreground/85">
        {content}
      </p>
    );
  }

  return (
    <p className="m-0 whitespace-pre-wrap text-[15px] leading-7 text-foreground/90">
      {content}
    </p>
  );
}

function AnnotationInspector<TKind extends string, TRef>({
  annotationIds,
  annotationsById,
  selectedId,
  connection,
  onSelectId,
  renderInspector,
}: {
  annotationIds: string[];
  annotationsById: Map<string, DocumentAnnotation<TKind, TRef>>;
  selectedId: string | null;
  connection: DocumentTraceConnection;
  onSelectId: (id: string) => void;
  renderInspector: (
    annotation: DocumentAnnotation<TKind, TRef>,
    connection: DocumentTraceConnection,
  ) => ReactNode;
}) {
  const annotations = annotationIds
    .map((id) => annotationsById.get(id))
    .filter((annotation): annotation is DocumentAnnotation<TKind, TRef> => Boolean(annotation));
  const selected = annotations.find((annotation) => annotation.id === selectedId) ?? annotations[0] ?? null;

  if (!selected) {
    return (
      <div className="flex min-h-56 flex-col items-center justify-center px-6 text-center">
        <FileText className="h-5 w-5 text-muted-foreground" aria-hidden="true" />
        <p className="mt-3 text-sm font-medium text-foreground">Select a connection</p>
        <p className="mt-1 max-w-56 text-xs leading-5 text-muted-foreground">
          Choose a highlighted passage or gutter marker to inspect the saved result connected to it.
        </p>
      </div>
    );
  }

  return (
    <div>
      {annotations.length > 1 && (
        <div className="border-b border-border/80 px-4 py-3">
          <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
            Connected results · {annotations.length}
          </p>
          <div className="max-h-60 space-y-1 overflow-y-auto overscroll-contain pr-1">
            {annotations.map((annotation) => (
              <button
                key={annotation.id}
                type="button"
                onClick={() => onSelectId(annotation.id)}
                aria-pressed={annotation.id === selected.id}
                aria-label={`View ${annotation.layerLabel}: ${annotation.title}`}
                className={cn(
                  "grid min-h-11 w-full min-w-0 grid-cols-[7.5rem_minmax(0,1fr)] items-center gap-2 rounded-md border px-2.5 py-1.5 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/30 motion-reduce:transition-none",
                  annotation.id === selected.id
                    ? "border-foreground/15 bg-muted/70 text-foreground"
                    : "border-border bg-background text-muted-foreground hover:bg-muted hover:text-foreground",
                )}
              >
                <span className="truncate text-[10px] font-semibold uppercase tracking-[0.08em]">
                  {annotation.layerLabel}
                </span>
                <span className="truncate text-xs font-medium">{annotation.title}</span>
              </button>
            ))}
          </div>
        </div>
      )}
      {renderInspector(selected, connection)}
    </div>
  );
}

export function DocumentTraceViewer<TKind extends string, TRef>({
  blocks,
  annotations,
  layers,
  renderInspector,
  focusBlockId,
  onFocusBlockConsumed,
}: DocumentTraceViewerProps<TKind, TRef>) {
  const [layer, setLayer] = useState<TKind | "all">("all");
  const [documentId, setDocumentId] = useState("");
  const [activeAnnotationIds, setActiveAnnotationIds] = useState<string[]>([]);
  const [selectedAnnotationId, setSelectedAnnotationId] = useState<string | null>(null);
  const [connection, setConnection] = useState<DocumentTraceConnection>({ type: "block" });
  const [containerWidth, setContainerWidth] = useState(0);
  const [focusedBlockId, setFocusedBlockId] = useState<string | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const sheetRef = useRef<HTMLDivElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const selectionTriggerRef = useRef<HTMLElement | null>(null);
  const sheetWasOpenRef = useRef(false);
  const blockRefs = useRef(new Map<string, HTMLElement>());

  const visibleAnnotations = useMemo(
    () => filterDocumentAnnotations(annotations, layer),
    [annotations, layer],
  );
  const trace = useMemo(
    () => buildDocumentTrace(blocks, visibleAnnotations),
    [blocks, visibleAnnotations],
  );
  const fullTrace = useMemo(
    () => buildDocumentTrace(blocks, annotations),
    [annotations, blocks],
  );
  const annotationsById = useMemo(
    () => new Map(visibleAnnotations.map((annotation) => [annotation.id, annotation])),
    [visibleAnnotations],
  );
  const activeDocumentId = trace.documents.some((document) => document.docId === documentId)
    ? documentId
    : trace.documents[0]?.docId ?? "";
  const activeDocument = trace.documents.find((document) => document.docId === activeDocumentId) ?? null;
  const unresolvedAnnotations = trace.unresolvedAnnotationIds
    .map((id) => annotationsById.get(id))
    .filter((annotation): annotation is DocumentAnnotation<TKind, TRef> => Boolean(annotation));
  const isNarrow = containerWidth < 1024;
  const railMode = documentTraceRailMode(containerWidth);

  useEffect(() => {
    if (!focusBlockId) return;
    const focusTarget = documentTraceFocusTarget(fullTrace, focusBlockId);
    if (!focusTarget) {
      onFocusBlockConsumed?.(focusBlockId);
      return;
    }
    if (focusTarget.documentId !== activeDocumentId) {
      setDocumentId(focusTarget.documentId);
      return;
    }
    if (
      focusTarget.selectedAnnotationId
      && !annotationsById.has(focusTarget.selectedAnnotationId)
      && layer !== "all"
    ) {
      setLayer("all");
      return;
    }
    const trigger = blockRefs.current.get(focusBlockId);
    if (!trigger) return;

    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    trigger.scrollIntoView({
      behavior: reduceMotion ? "auto" : "smooth",
      block: "center",
      inline: "nearest",
    });
    trigger.focus({ preventScroll: true });
    selectionTriggerRef.current = trigger;
    setFocusedBlockId(focusBlockId);
    if (focusTarget.selectedAnnotationId && focusTarget.connection) {
      setActiveAnnotationIds(focusTarget.annotationIds);
      setSelectedAnnotationId(focusTarget.selectedAnnotationId);
      setConnection(focusTarget.connection);
    } else {
      setActiveAnnotationIds([]);
      setSelectedAnnotationId(null);
      setConnection({ type: "block", blockId: focusBlockId });
    }
    onFocusBlockConsumed?.(focusBlockId);
  }, [
    activeDocumentId,
    annotationsById,
    focusBlockId,
    fullTrace,
    layer,
    onFocusBlockConsumed,
  ]);

  useEffect(() => {
    if (!focusedBlockId) return;
    const timeout = window.setTimeout(() => setFocusedBlockId(null), 2200);
    return () => window.clearTimeout(timeout);
  }, [focusedBlockId]);

  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;
    const update = (width: number) => setContainerWidth(width);
    update(root.getBoundingClientRect().width);
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (entry) update(entry.contentRect.width);
    });
    observer.observe(root);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const visibleIds = new Set(visibleAnnotations.map((annotation) => annotation.id));
    const nextActive = activeAnnotationIds.filter((id) => visibleIds.has(id));
    if (nextActive.length !== activeAnnotationIds.length) {
      setActiveAnnotationIds(nextActive);
    }
    if (selectedAnnotationId && !visibleIds.has(selectedAnnotationId)) {
      setSelectedAnnotationId(nextActive[0] ?? null);
    }
  }, [activeAnnotationIds, selectedAnnotationId, visibleAnnotations]);

  const sheetOpen = isNarrow && Boolean(selectedAnnotationId);

  useEffect(() => {
    if (!sheetOpen) {
      sheetWasOpenRef.current = false;
      return;
    }
    if (!sheetWasOpenRef.current) closeButtonRef.current?.focus();
    sheetWasOpenRef.current = true;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        closeInspector();
        return;
      }
      if (event.key !== "Tab" || !sheetRef.current) return;
      const focusable = [...sheetRef.current.querySelectorAll<HTMLElement>(
        'button:not([disabled]), a[href], select:not([disabled]), [tabindex]:not([tabindex="-1"])',
      )];
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [sheetOpen]);

  function selectAnnotations(
    ids: string[],
    trigger: HTMLElement,
    nextConnection: DocumentTraceConnection,
  ) {
    const availableIds = ids.filter((id) => annotationsById.has(id));
    if (!availableIds.length) return;
    selectionTriggerRef.current = trigger;
    setActiveAnnotationIds(availableIds);
    setSelectedAnnotationId(availableIds[0]);
    setConnection(nextConnection);
  }

  function closeInspector() {
    setActiveAnnotationIds([]);
    setSelectedAnnotationId(null);
    window.requestAnimationFrame(() => selectionTriggerRef.current?.focus());
  }

  if (!blocks.length) {
    return (
      <div className="flex min-h-80 flex-col items-center justify-center px-6 py-16 text-center">
        <FileText className="h-6 w-6 text-muted-foreground" aria-hidden="true" />
        <h3 className="mt-4 text-sm font-semibold text-foreground">Source document unavailable</h3>
        <p className="mt-1 max-w-sm text-sm leading-6 text-muted-foreground">
          This result does not contain retained source passages, so a document trace cannot be reconstructed.
        </p>
      </div>
    );
  }

  return (
    <div ref={rootRef} className="bg-muted/10">
      <div className={cn(
        "flex gap-3 border-b border-border/80 bg-card px-5 py-3 sm:px-6",
        isNarrow ? "flex-col" : "items-center",
      )}>
        <div className="flex min-w-0 flex-1 items-center gap-2">
          <Layers3 className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
          <p className="text-xs font-medium text-foreground">Document trace</p>
          <span className="text-[11px] tabular-nums text-muted-foreground" role="status">
            {visibleAnnotations.length} {visibleAnnotations.length === 1 ? "connection" : "connections"}
          </span>
        </div>
        <div className={cn("flex gap-2", isNarrow ? "flex-col" : "flex-row")}>
          {trace.documents.length > 1 && (
            <Select value={activeDocumentId} onValueChange={setDocumentId}>
              <SelectTrigger className={cn("h-8 bg-card text-xs", isNarrow ? "w-full" : "w-52")} aria-label="Source document">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {trace.documents.map((document) => (
                  <SelectItem key={document.docId} value={document.docId}>
                    {displayDocumentName(document.docId)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
          <Select value={layer} onValueChange={(value) => setLayer(value as TKind | "all")}>
            <SelectTrigger className={cn("h-8 bg-card text-xs", isNarrow ? "w-full" : "w-52")} aria-label="Trace layer">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All result layers</SelectItem>
              {layers.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {unresolvedAnnotations.length > 0 && (
        <details className="border-b border-border/80 bg-card px-5 py-3 sm:px-6">
          <summary className="cursor-pointer text-xs font-medium text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/30">
            Unavailable source connections · {unresolvedAnnotations.length}
          </summary>
          <p className="mt-2 max-w-2xl text-xs leading-5 text-muted-foreground">
            These saved results cite blocks that are not present in the retained document. They remain inspectable but are not placed in the reconstructed text.
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            {unresolvedAnnotations.map((annotation) => (
              <button
                key={annotation.id}
                type="button"
                onClick={(event) => selectAnnotations([annotation.id], event.currentTarget, {
                  type: "unavailable",
                  unavailableBlockIds: trace.unresolvedBlockIdsByAnnotation[annotation.id] ?? [],
                })}
                aria-label={`Inspect unavailable ${annotation.layerLabel}: ${annotation.title}`}
                className="min-h-8 rounded-md border border-border/80 bg-background px-2.5 py-1 text-left text-[11px] font-medium text-muted-foreground transition-colors hover:border-foreground/20 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/30 motion-reduce:transition-none"
              >
                {annotation.layerLabel} · {annotation.title}
              </button>
            ))}
          </div>
        </details>
      )}

      <div className={cn(
        "grid min-h-[38rem]",
        !isNarrow && "grid-cols-[minmax(0,1fr)_22rem]",
      )}>
        <div className={cn(
          "max-h-[min(76vh,58rem)] overflow-y-auto overscroll-contain bg-muted/20 py-6",
          isNarrow ? "px-3 sm:px-6" : "px-8",
        )}>
          <article
            aria-label={`Reconstructed source document: ${displayDocumentName(activeDocumentId)}`}
            className={cn(
              "relative mx-auto min-h-full",
              railMode === "inline"
                ? "max-w-[52rem] rounded-lg bg-card px-5 py-8 shadow-[0_1px_2px_hsl(var(--foreground)/0.04),0_14px_36px_hsl(var(--foreground)/0.035)] sm:px-10 sm:py-12"
                : "max-w-[60rem] py-12",
            )}
          >
            {railMode === "external" && (
              <div
                aria-hidden="true"
                className="pointer-events-none absolute inset-y-0 left-[7.25rem] right-0 rounded-lg bg-card shadow-[0_1px_2px_hsl(var(--foreground)/0.04),0_14px_36px_hsl(var(--foreground)/0.035)]"
              />
            )}
            {activeDocument?.blocks.map((traceBlock, blockIndex) => {
              const markerGroups = groupDocumentTraceMarkers(traceBlock.markers);
              const spacing = documentBlockSpacing(documentBlockPresentation(traceBlock.block));
              return (
                <section
                  ref={(element) => {
                    if (element) blockRefs.current.set(traceBlock.block.id, element);
                    else blockRefs.current.delete(traceBlock.block.id);
                  }}
                  key={traceBlock.block.id}
                  data-block-id={traceBlock.block.id}
                  tabIndex={-1}
                  className={cn(
                    "group/trace-block relative grid scroll-mt-6 outline-none",
                    blockIndex > 0 && blockSpacingClass(spacing),
                    railMode === "inline"
                      ? "grid-cols-1 gap-1"
                      : "grid-cols-[6rem_minmax(0,1fr)] gap-5",
                  )}
                  style={{ contentVisibility: "auto", containIntrinsicSize: "auto 72px" }}
                >
                  <div className={cn(
                    "relative z-10 flex min-w-0 flex-row flex-wrap items-center gap-1",
                    railMode === "inline"
                      ? "mb-2"
                      : "justify-end self-start pt-1",
                  )}>
                    <BlockReferenceId
                      blockId={traceBlock.block.id}
                      className="inline-flex h-6 max-w-full items-center px-1 text-[10px] text-muted-foreground/50 transition-colors group-hover/trace-block:text-muted-foreground motion-reduce:transition-none"
                    />
                    {markerGroups.map((group) => {
                      const isActive = group.annotationIds.some((id) => activeAnnotationIds.includes(id));
                      const label = markerGroupLabel(group.reason, group.annotationIds.length);
                      return (
                        <button
                          key={group.reason}
                          type="button"
                          onClick={(event) => selectAnnotations(group.annotationIds, event.currentTarget, {
                            type: "block",
                            blockId: traceBlock.block.id,
                            markerReason: group.reason,
                            unmatchedQuotes: group.unmatchedQuotes,
                          })}
                          aria-pressed={isActive}
                          aria-label={`View ${label} connected to source passage ${traceBlock.block.id}`}
                          className={cn(
                            "inline-flex h-6 min-w-6 items-center justify-center gap-1 rounded-md border border-border/70 bg-background px-1.5 text-[10px] font-medium text-muted-foreground transition-colors hover:border-foreground/20 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/30 motion-reduce:transition-none",
                            isActive && "border-foreground/25 bg-foreground text-background",
                          )}
                          title={label}
                        >
                          <Link2 aria-hidden="true" className="h-3 w-3 shrink-0" />
                          <span className="tabular-nums">{group.annotationIds.length}</span>
                        </button>
                      );
                    })}
                  </div>
                  <div className={cn(
                    "relative z-10 min-w-0 rounded-md transition-[background-color,box-shadow] duration-slow group-hover/trace-block:bg-muted/35 group-focus-within/trace-block:bg-muted/35 motion-reduce:transition-none",
                    railMode === "external" && "px-10 py-1",
                    focusedBlockId === traceBlock.block.id && "bg-amber-100/75 shadow-[0_0_0_1px_rgb(245_158_11/0.28),0_0_0_7px_rgb(251_191_36/0.10),0_10px_28px_rgb(245_158_11/0.10)] dark:bg-amber-300/15",
                  )}>
                    <BlockText
                      traceBlock={traceBlock}
                      annotationsById={annotationsById}
                      activeAnnotationIds={activeAnnotationIds}
                      onSelect={selectAnnotations}
                    />
                  </div>
                </section>
              );
            })}
            {activeDocument && visibleAnnotations.length === 0 && (
              <p className="mt-8 rounded-md bg-muted/40 px-4 py-3 text-center text-xs leading-5 text-muted-foreground">
                This layer has no source connections in the saved result. The full retained document remains visible.
              </p>
            )}
          </article>
        </div>

        {!isNarrow && (
          <aside className="border-l border-border/80 bg-card" aria-label="Trace details">
            <div className="sticky top-0 max-h-[min(76vh,58rem)] overflow-y-auto overscroll-contain">
              <AnnotationInspector
                annotationIds={activeAnnotationIds}
                annotationsById={annotationsById}
                selectedId={selectedAnnotationId}
                connection={connection}
                onSelectId={setSelectedAnnotationId}
                renderInspector={renderInspector}
              />
            </div>
          </aside>
        )}
      </div>

      {isNarrow && selectedAnnotationId && (
        <div className="fixed inset-0 z-50" role="presentation">
          <button
            type="button"
            className="absolute inset-0 bg-foreground/20 backdrop-blur-[1px]"
            onClick={closeInspector}
            aria-label="Close trace details"
          />
          <div
            ref={sheetRef}
            role="dialog"
            aria-modal="true"
            aria-label="Trace details"
            className="absolute inset-x-3 bottom-3 max-h-[min(76vh,42rem)] overflow-y-auto overscroll-contain rounded-xl bg-card shadow-[0_20px_60px_hsl(var(--foreground)/0.22)] outline outline-1 outline-black/10 dark:outline-white/10"
          >
            <TracePanelHeader
              eyebrow="Document trace"
              title="Connected result"
              description="Inspect the saved result linked to the selected source passage."
              className="sticky top-0 z-10 bg-card/95 backdrop-blur"
              action={(
                <button
                  ref={closeButtonRef}
                  type="button"
                  onClick={closeInspector}
                  className="inline-flex h-9 w-9 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/30 motion-reduce:transition-none"
                  aria-label="Close trace details"
                >
                  <X className="h-4 w-4" aria-hidden="true" />
                </button>
              )}
            />
            <AnnotationInspector
              annotationIds={activeAnnotationIds}
              annotationsById={annotationsById}
              selectedId={selectedAnnotationId}
              connection={connection}
              onSelectId={setSelectedAnnotationId}
              renderInspector={renderInspector}
            />
          </div>
        </div>
      )}
    </div>
  );
}
