"use client";

import {
  type ReactNode,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { CircleDashed, FileText, Layers3, Link2, X } from "lucide-react";
import { BlockReferenceId } from "@/components/block-reference";
import { TracePanelHeader } from "@/components/document-trace-panel";
import type { ContentBlock } from "@/lib/api";
import {
  documentBlockPresentation,
  documentBlockSpacing,
  documentTableCells,
  type DocumentBlockSpacing,
  documentTracePanelMode,
  documentTraceRailMode,
} from "@/lib/document-block-presentation";
import {
  buildDocumentTrace,
  displayDocumentName,
  documentTraceBlockLocation,
  documentTracePassages,
  documentTraceSegmentsInRange,
  filterDocumentAnnotations,
  groupDocumentTraceMarkers,
  type DocumentAnnotation,
  type DocumentAnnotationEmphasis,
  type DocumentTraceConnection,
  type DocumentTraceBlock,
  type DocumentTracePassage,
  type DocumentTraceSegment,
} from "@/lib/document-trace";
import { ARRIVAL_HIGHLIGHT, ARRIVAL_HIGHLIGHT_MS } from "@/lib/motion";
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

/**
 * What an inspector needs to account for its own lineage: the passages the result was
 * read from, and a way to show one.
 *
 * The viewer supplies both because it owns the things a jump requires — the document
 * switcher, the rendered blocks, the scroll container. An inspector holds one
 * annotation and cannot resolve a block id on its own, which is why the count was all
 * it could ever render.
 */
export type DocumentTracePassageAccess = {
  passages: DocumentTracePassage[];
  /**
   * Scrolls to a passage of the result already open. Deliberately not a selection
   * change: moving between the passages of one result must not change which result
   * you are reading, so this switches documents and scrolls, and nothing else.
   */
  reveal: (blockId: string) => void;
};

export type DocumentTraceViewerProps<TKind extends string, TRef> = {
  blocks: ContentBlock[];
  annotations: Array<DocumentAnnotation<TKind, TRef>>;
  layers: Array<LayerOption<TKind>>;
  /**
   * Layer selected on open. Defaults to showing every layer at once.
   *
   * A tool whose annotations carry `emphasis` should name one, because block
   * emphasis is suppressed while several layers are visible — see below.
   */
  defaultLayer?: TKind;
  renderInspector: (
    annotation: DocumentAnnotation<TKind, TRef>,
    connection: DocumentTraceConnection,
    passages: DocumentTracePassageAccess,
  ) => ReactNode;
  focusBlockId?: string | null;
  onFocusBlockConsumed?: (blockId: string) => void;
};

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

/**
 * Whole-block emphasis surfaces, kept faint: the document must stay readable, and
 * the grade itself is carried as text in the badge rather than by colour.
 */
const EMPHASIS_SURFACE_CLASS: Record<DocumentAnnotationEmphasis["tone"], string> = {
  success: "bg-[hsl(var(--tone-success))]/[0.07]",
  caution: "bg-[hsl(var(--tone-warning))]/[0.07]",
  danger: "bg-[hsl(var(--tone-danger))]/[0.07]",
  neutral: "bg-[hsl(var(--tone-neutral))]/[0.05]",
};

/**
 * The badge over a marked block.
 *
 * Opaque, not translucent. It sits in the bottom corner of the block, so a tinted
 * background let the block's own text show through the label and the two competed at
 * exactly the point a reader was trying to read one of them. Solid means the label wins
 * while it is there — and it stops being there on hover, which is when the reader wants
 * the sentence underneath instead. That is the same trade the block tint already makes.
 */
const EMPHASIS_BADGE_CLASS: Record<DocumentAnnotationEmphasis["tone"], string> = {
  success:
    "border-[hsl(var(--tone-success))]/45 bg-[hsl(var(--tone-success))] text-white dark:text-background",
  caution:
    "border-[hsl(var(--tone-warning))]/45 bg-[hsl(var(--tone-warning))] text-white dark:text-background",
  danger:
    "border-[hsl(var(--tone-danger))]/45 bg-[hsl(var(--tone-danger))] text-white dark:text-background",
  neutral: "border-border bg-muted text-foreground",
};

/**
 * Narrowest a table column may become before its row scrolls sideways instead.
 *
 * Sized for prose values rather than short numbers: these cells routinely carry
 * a sentence, and below roughly this width a sentence breaks into one or two
 * words per line.
 */
const TABLE_COLUMN_MIN_REM = 13;

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
          // One marking token for both tools. Scout marks an exact span here;
          // Inspector marks a whole block below. Same meaning, same colour.
          "inline box-decoration-clone rounded-[3px] bg-[hsl(var(--tone-marked))]/25 px-0.5 text-left text-inherit transition-colors hover:bg-[hsl(var(--tone-marked))]/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(var(--tone-marked))]/45 motion-reduce:transition-none",
          isActive && "bg-[hsl(var(--tone-marked))]/50 ring-1 ring-[hsl(var(--tone-marked))]/40",
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

/**
 * Findings about content that is not in the document, drawn at the end of the
 * section they belong to.
 *
 * Deliberately not in the gutter. Incompleteness is a property of a section, not
 * of a block, and a control sitting beside one block reads as attached to that
 * block's text however it is styled. A full-width row is visibly scoped to the
 * region instead, and naming the section makes the row explain itself.
 *
 * It sits inside the paper because a gap belongs to the document's substance, but
 * carries no block ID and no highlight, because it cites nothing.
 */
function SectionGapRow<TKind extends string, TRef>({
  annotations,
  sectionLabel,
  activeAnnotationIds,
  onSelect,
}: {
  annotations: Array<DocumentAnnotation<TKind, TRef>>;
  sectionLabel: string | null;
  activeAnnotationIds: string[];
  onSelect: (
    annotationIds: string[],
    trigger: HTMLElement,
    connection: DocumentTraceConnection,
  ) => void;
}) {
  const isActive = annotations.some((annotation) =>
    activeAnnotationIds.includes(annotation.id));
  const scope = sectionLabel?.trim();
  const label = scope
    ? `Not present in ${scope}`
    : "Not present in this section";

  return (
    // Ruled above and below, so the row reads as something inserted between two
    // passages rather than a note trailing the one above it. That is the honest
    // shape: the gap belongs to the seam, not to either neighbour.
    <div className="my-4 border-y border-dashed border-[hsl(var(--tone-warning))]/35 py-3">
      <button
        type="button"
        onClick={(event) => onSelect(
          annotations.map((annotation) => annotation.id),
          event.currentTarget,
          { type: "unavailable" },
        )}
        aria-pressed={isActive}
        aria-label={`View ${annotations.length} ${
          annotations.length === 1 ? "item" : "items"
        } not present in ${scope ?? "this section"}`}
        className={cn(
          "inline-flex min-h-7 items-center gap-2 rounded-md border border-dashed px-2 py-1 text-left text-[11px] font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/30 motion-reduce:transition-none",
          "border-[hsl(var(--tone-warning))]/40 text-[hsl(var(--tone-warning))] hover:border-[hsl(var(--tone-warning))]/70 hover:bg-[hsl(var(--tone-warning))]/[0.06]",
          isActive && "border-[hsl(var(--tone-warning))] bg-[hsl(var(--tone-warning))]/10",
        )}
      >
        <CircleDashed aria-hidden="true" className="h-3.5 w-3.5 shrink-0" />
        <span>{label}</span>
        <span className="tabular-nums opacity-70">· {annotations.length}</span>
      </button>
    </div>
  );
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
              // Every column of a multi-column row gets a readable floor, and the
              // wrapper scrolls sideways when they no longer fit. Previously only
              // rows with more than three columns had a floor, so a three-column
              // row of prose compressed into tall thin strips — and it compressed
              // differently depending on whether the detail panel was open, which
              // made the same passage read two ways.
              minWidth: tableRow.columnCount > 1
                ? `${tableRow.columnCount * TABLE_COLUMN_MIN_REM}rem`
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
  passagesFor,
  onReveal,
  renderInspector,
}: {
  annotationIds: string[];
  annotationsById: Map<string, DocumentAnnotation<TKind, TRef>>;
  selectedId: string | null;
  connection: DocumentTraceConnection;
  onSelectId: (id: string) => void;
  passagesFor: (annotationId: string) => DocumentTracePassage[];
  onReveal: (blockId: string) => void;
  renderInspector: (
    annotation: DocumentAnnotation<TKind, TRef>,
    connection: DocumentTraceConnection,
    passages: DocumentTracePassageAccess,
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
      {renderInspector(selected, connection, {
        passages: passagesFor(selected.id),
        reveal: onReveal,
      })}
    </div>
  );
}

export function DocumentTraceViewer<TKind extends string, TRef>({
  blocks,
  annotations,
  layers,
  defaultLayer,
  renderInspector,
  focusBlockId,
  onFocusBlockConsumed,
}: DocumentTraceViewerProps<TKind, TRef>) {
  const [layer, setLayer] = useState<TKind | "all">(defaultLayer ?? "all");
  /**
   * Emphasis is a claim on one axis. Tinting a block while several layers are
   * visible would blend independent judgments into a single colour — a composite
   * verdict no individual result made. Markers and gap counts stay visible, so
   * structure still reads; choosing a layer reveals that layer's emphasis.
   */
  const emphasisVisible = layer !== "all";
  const [documentId, setDocumentId] = useState("");
  const [activeAnnotationIds, setActiveAnnotationIds] = useState<string[]>([]);
  const [selectedAnnotationId, setSelectedAnnotationId] = useState<string | null>(null);
  const [connection, setConnection] = useState<DocumentTraceConnection>({ type: "block" });
  const [containerWidth, setContainerWidth] = useState(0);
  const [focusedBlockId, setFocusedBlockId] = useState<string | null>(null);
  const [revealBlockId, setRevealBlockId] = useState<string | null>(null);
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
  // Every annotation, not just the visible ones: the reveal below has to look up the
  // layer of a mark the current filter is hiding, which is precisely the case it exists
  // to handle.
  const allAnnotationsById = useMemo(
    () => new Map(annotations.map((annotation) => [annotation.id, annotation])),
    [annotations],
  );
  const activeDocumentId = trace.documents.some((document) => document.docId === documentId)
    ? documentId
    : trace.documents[0]?.docId ?? "";
  const activeDocument = trace.documents.find((document) => document.docId === activeDocumentId) ?? null;
  const unresolvedAnnotations = trace.unresolvedAnnotationIds
    .map((id) => annotationsById.get(id))
    .filter((annotation): annotation is DocumentAnnotation<TKind, TRef> => Boolean(annotation));
  const unplacedAnnotations = trace.unplacedAnnotationIds
    .map((id) => annotationsById.get(id))
    .filter((annotation): annotation is DocumentAnnotation<TKind, TRef> => Boolean(annotation));
  // "Does the panel fit beside the document" — decided by the two columns' own widths,
  // not by a viewport breakpoint no page's container can clear. See the helper.
  const isNarrow = documentTracePanelMode(containerWidth) === "sheet";
  const railMode = documentTraceRailMode(containerWidth);

  /**
   * Show one passage: switch document if it lives in another one, scroll it to the
   * middle, and ring it. Nothing else.
   *
   * One path for both callers — a result row handing in `focusBlockId`, and the panel's
   * own passage list — because they are the same act, and two paths meant one click
   * behaved differently depending on where it came from.
   *
   * It deliberately selects nothing. Opening the details panel on arrival put a reader
   * in front of a panel restating the row they had just left, and on a narrow container
   * that panel is a sheet covering the passage it was sent to reveal. Arrival centres
   * the block; opening its result stays a second, deliberate click on the mark.
   */
  useEffect(() => {
    const blockId = focusBlockId ?? revealBlockId;
    if (!blockId) return;
    const done = () => {
      if (focusBlockId) onFocusBlockConsumed?.(focusBlockId);
      setRevealBlockId(null);
    };
    const location = documentTraceBlockLocation(fullTrace, blockId);
    if (!location) {
      done();
      return;
    }
    // A cited passage can live in another uploaded document. Switch first, then let
    // this run again once that document's blocks are mounted.
    if (location.documentId !== activeDocumentId) {
      setDocumentId(location.documentId);
      return;
    }
    // The layer filter can be hiding every mark on the block, and arriving at an
    // apparently unmarked passage reads as a broken link. So the view moves to where the
    // passage lives: to its own layer when its marks are all of one kind, which is the
    // common case and the more useful landing — a reader sent to an answered passage
    // wants the answered view, not every layer at once. Only a passage marked by two
    // different kinds falls back to `all`, because there is no single right layer for it.
    if (
      layer !== "all"
      && location.annotationIds.length > 0
      && !location.annotationIds.some((id) => annotationsById.has(id))
    ) {
      const kinds = new Set(
        location.annotationIds
          .map((id) => allAnnotationsById.get(id)?.kind)
          .filter((kind): kind is TKind => Boolean(kind)),
      );
      const [only] = [...kinds];
      setLayer(kinds.size === 1 && layers.some((option) => option.value === only)
        ? only
        : "all");
      return;
    }
    const target = blockRefs.current.get(blockId);
    // Cleared rather than left pending: the request is retried across the switches
    // above, so by here the block is either mounted or not in this document. Holding a
    // request that can never complete would make a second click on the same passage a
    // no-op, because the state would not change.
    if (!target) {
      done();
      return;
    }

    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    target.scrollIntoView({
      behavior: reduceMotion ? "auto" : "smooth",
      block: "center",
      inline: "nearest",
    });
    target.focus({ preventScroll: true });
    selectionTriggerRef.current = target;
    setFocusedBlockId(blockId);
    done();
  }, [
    activeDocumentId,
    allAnnotationsById,
    annotationsById,
    focusBlockId,
    fullTrace,
    layer,
    layers,
    onFocusBlockConsumed,
    revealBlockId,
  ]);

  useEffect(() => {
    if (!focusedBlockId) return;
    const timeout = window.setTimeout(
      () => setFocusedBlockId(null),
      ARRIVAL_HIGHLIGHT_MS,
    );
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

  /**
   * Read from `fullTrace`, not the filtered one: a result's own passages are its
   * lineage regardless of which layer is on display, and resolving them against the
   * visible subset would drop citations for no reason the reader could see.
   */
  function passagesFor(annotationId: string): DocumentTracePassage[] {
    return documentTracePassages(fullTrace, annotationId);
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

      {unplacedAnnotations.length > 0 && (
        <details className="border-b border-border/80 bg-card px-5 py-3 sm:px-6">
          <summary className="cursor-pointer text-xs font-medium text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/30">
            Not located in this document · {unplacedAnnotations.length}
          </summary>
          <p className="mt-2 max-w-2xl text-xs leading-5 text-muted-foreground">
            These results describe content that is absent, so they cite no source
            passage and cannot be placed in the reconstructed text.
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            {unplacedAnnotations.map((annotation) => (
              <button
                key={annotation.id}
                type="button"
                onClick={(event) => selectAnnotations([annotation.id], event.currentTarget, {
                  type: "unavailable",
                })}
                aria-label={`Inspect ${annotation.layerLabel}: ${annotation.title}`}
                className="min-h-8 rounded-md border border-border/80 bg-background px-2.5 py-1 text-left text-[11px] font-medium text-muted-foreground transition-colors hover:border-foreground/20 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/30 motion-reduce:transition-none"
              >
                {annotation.layerLabel} · {annotation.title}
                {annotation.statusLabel ? ` · ${annotation.statusLabel}` : ""}
              </button>
            ))}
          </div>
        </details>
      )}

      <div className={cn(
        "grid min-h-[38rem]",
        // The panel is present only while something is selected, so closing it
        // returns the width to the document rather than leaving a dead column.
        !isNarrow && (selectedAnnotationId ? "grid-cols-[minmax(0,1fr)_22rem]" : "grid-cols-1"),
      )}>
        <div
          className={cn(
            "max-h-[min(76vh,58rem)] overflow-y-auto overscroll-contain bg-muted/20 py-6",
            isNarrow ? "px-3 sm:px-6" : "px-8",
          )}
        >
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
              // A block becomes its own click target when it carries a visible
              // mark and no span buttons of its own to nest inside.
              const blockIsMarkTarget = Boolean(
                emphasisVisible
                  && traceBlock.emphasis
                  && markerGroups.length > 0
                  && !traceBlock.segments.some((segment) => segment.annotationIds.length > 0),
              );
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
                    // Arrival is a transient outline, not a fill: a filled block
                    // already means "a result marks this", and the two always coincide
                    // — a jump can only land on a cited block. On the row rather than
                    // its text so it rings the whole passage, gutter included, and
                    // survives the row's own paint containment.
                    "transition-shadow duration-slow motion-reduce:transition-none",
                    focusedBlockId === traceBlock.block.id && ARRIVAL_HIGHLIGHT,
                    railMode === "inline"
                      ? "grid-cols-1 gap-1"
                      : "grid-cols-[6rem_minmax(0,1fr)] gap-5",
                  )}
                  /* No `content-visibility: auto` here. It skips rendering an offscreen
                     block and substitutes a fixed placeholder height, so a block that had
                     never been painted counted as 72px however tall it really was. Every
                     scroll position computed from that was wrong: `scrollIntoView({ block:
                     "center" })` aimed using the estimates, the blocks above then painted
                     at their true heights, and the target ended up near the bottom of the
                     view — further off the deeper into the document the jump went. Its
                     paint containment also clipped anything drawn at a row's edge. Landing
                     on the right passage is what this view is for, and the browser gets
                     that exactly right when nothing misreports its own height. */
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
                    {/* Counts appear only for connections with no visible mark
                        in the paper. When the block itself is marked, the mark is
                        the target and a second control here would duplicate it. */}
                    {!blockIsMarkTarget && markerGroups.map((group) => {
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
                  <div
                    className={cn(
                      "relative z-10 min-w-0 rounded-md transition-[background-color,box-shadow] duration-slow motion-reduce:transition-none",
                      railMode === "external" && "px-10 py-1",
                      emphasisVisible
                        && traceBlock.emphasis
                        && EMPHASIS_SURFACE_CLASS[traceBlock.emphasis.tone],
                      "group-hover/trace-block:bg-muted/35 group-focus-within/trace-block:bg-muted/35",
                      blockIsMarkTarget
                        && "cursor-pointer hover:bg-[hsl(var(--tone-marked))]/10 focus-within:bg-[hsl(var(--tone-marked))]/10",
                    )}
                    onClick={blockIsMarkTarget ? (event) => {
                      // Selecting text inside a marked block must not open its
                      // detail, or the passage becomes impossible to quote.
                      if (!window.getSelection()?.isCollapsed) return;
                      const badge = event.currentTarget.querySelector("button");
                      if (badge instanceof HTMLElement) badge.click();
                    } : undefined}
                  >
                    <BlockText
                      traceBlock={traceBlock}
                      annotationsById={annotationsById}
                      activeAnnotationIds={activeAnnotationIds}
                      onSelect={selectAnnotations}
                    />
                    {blockIsMarkTarget && traceBlock.emphasis && (
                      // The grade is the focusable control; the surrounding block
                      // is a convenience target handled above. An overlay covering
                      // the block would be a larger hit area but would also make
                      // its text unselectable and swallow a wide table's sideways
                      // drag, so the affordance stays out of the content's way.
                      <button
                        type="button"
                        onClick={(event) => selectAnnotations(
                          markerGroups.flatMap((group) => group.annotationIds),
                          event.currentTarget,
                          { type: "block", blockId: traceBlock.block.id, markerReason: "block_only" },
                        )}
                        aria-pressed={markerGroups.some((group) =>
                          group.annotationIds.some((id) => activeAnnotationIds.includes(id)))}
                        aria-label={`View the result marking source passage ${traceBlock.block.id}, graded ${traceBlock.emphasis.badge ?? "unrated"}`}
                        className={cn(
                          "absolute bottom-1.5 right-2 z-10 inline-flex h-5 min-w-5 items-center justify-center rounded border px-1 text-[10px] font-semibold tabular-nums transition-opacity duration-base focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40 motion-reduce:transition-none",
                          // Hidden while the block is hovered or focused, so the text it
                          // covers is readable without moving the label somewhere it
                          // would no longer read as belonging to this block. Kept
                          // visible on keyboard focus of the badge itself, or it would
                          // vanish under the cursor that is about to click it.
                          "group-hover/trace-block:opacity-0 group-focus-within/trace-block:opacity-0 focus-visible:!opacity-100",
                          EMPHASIS_BADGE_CLASS[traceBlock.emphasis.tone],
                        )}
                      >
                        {traceBlock.emphasis.badge}
                      </button>
                    )}
                  </div>
                  {traceBlock.anchored.length > 0 && (
                    // Its own grid row, outside the block body: inside it, the row
                    // would sit on the block's emphasis tint and borrow that
                    // block's grade colour — re-attaching the gap to a passage it
                    // does not describe.
                    <div className={cn(
                      "relative z-10 min-w-0",
                      railMode === "external" && "col-start-2 px-10",
                    )}>
                      <SectionGapRow
                        annotations={traceBlock.anchored}
                        sectionLabel={traceBlock.block.section_label}
                        activeAnnotationIds={activeAnnotationIds}
                        onSelect={selectAnnotations}
                      />
                    </div>
                  )}
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

        {!isNarrow && selectedAnnotationId && (
          <aside className="border-l border-border/80 bg-card" aria-label="Trace details">
            <div className="sticky top-0 max-h-[min(76vh,58rem)] overflow-y-auto overscroll-contain">
              <div className="flex justify-end border-b border-border/80 px-2 py-2">
                <button
                  type="button"
                  onClick={closeInspector}
                  aria-label="Close trace details"
                  className="inline-flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/30 motion-reduce:transition-none"
                >
                  <X className="h-4 w-4" aria-hidden="true" />
                </button>
              </div>
              <AnnotationInspector
                annotationIds={activeAnnotationIds}
                annotationsById={annotationsById}
                selectedId={selectedAnnotationId}
                connection={connection}
                onSelectId={setSelectedAnnotationId}
                passagesFor={passagesFor}
                onReveal={setRevealBlockId}
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
              passagesFor={passagesFor}
              onReveal={setRevealBlockId}
              renderInspector={renderInspector}
            />
          </div>
        </div>
      )}
    </div>
  );
}
