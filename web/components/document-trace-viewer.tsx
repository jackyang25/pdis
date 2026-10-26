"use client";

import type { TraceFocus } from "@/lib/trace-focus";
import {
  type CSSProperties,
  type ReactNode,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { CircleDashed, FileText, Link2, X } from "lucide-react";
import { TracePanelCloseProvider, TracePanelHeader } from "@/components/document-trace-panel";
import { DocumentVisual } from "@/components/document-visual";
import type { ContentBlock } from "@/lib/api";
import { groupDocumentTraceSurfaces } from "@/lib/document-trace-surfaces";
import {
  documentBlockPresentation,
  documentBlockSpacing,
  documentTableCells,
  documentTableRowContinues,
  tableHeaderLabel,
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
import { COUNT, DISPLAY_HEADING, EYEBROW } from "@/lib/typography";
import { DisclosureSummary } from "@/components/ui/disclosure-summary";
import { Reading } from "@/components/ui/evidence-text";
import { ReportFinding } from "@/components/report-finding";
import { compactBlockId } from "@/lib/block-reference";
import { countLabel } from "@/lib/count-label";

type LayerOption<TKind extends string> = {
  value: TKind;
  label: string;
};

function SourceSurfaceContent({ blocks, children, externalRail }: {
  blocks: Pick<DocumentTraceBlock, "block" | "markers" | "segments">[];
  children: ReactNode[];
  externalRail: boolean;
}) {
  const overview = (index: number) => Boolean(blocks[index].block.image
    && ["full_slide", "full_page"].includes(String(blocks[index].block.structural_meta.visual_scope)));
  if (!blocks.some((_, index) => overview(index))) return <>{children}</>;
  const visuals = children.filter((_, index) => overview(index));
  const text = children.filter((_, index) => !overview(index));
  // Open when a result marks the page's text. Closed, the mark was inside it: a reader saw
  // the page picture with nothing on it, and clicking the page opened nothing, because the
  // passage the answer cites is the page's extracted text, not its picture.
  const marked = blocks.some((traceBlock, index) => !overview(index) && (
    traceBlock.markers.length > 0 || traceBlock.segments.some((segment) => segment.annotationIds.length > 0)
  ));
  return <>
    {visuals}
    {text.length > 0 && <details data-source-text="true" open={marked} className="relative z-10 mt-5">
      <DisclosureSummary className={cn("w-fit rounded-md py-2 text-xs font-medium text-muted-foreground", externalRail && cn(PAPER_OFFSET, "px-10"))}>
        Extracted text and source blocks
      </DisclosureSummary>
      <div className="mt-4">{text}</div>
    </details>}
  </>;
}

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
  focus?: TraceFocus | null;
  onFocusConsumed?: (focus: TraceFocus) => void;
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
    return countLabel(count, "unmatched excerpt");
  }
  return countLabel(count, "linked result");
}

/**
 * Whole-block emphasis surfaces, kept faint: the document must stay readable, and
 * the grade itself is carried as text in the badge rather than by colour.
 */
const EMPHASIS_SURFACE_CLASS: Record<DocumentAnnotationEmphasis["tone"], string> = {
  success: "bg-[hsl(var(--tone-success))]/[0.07]",
  warning: "bg-[hsl(var(--tone-warning))]/[0.07]",
  danger: "bg-[hsl(var(--tone-danger))]/[0.07]",
  info: "bg-[hsl(var(--tone-info))]/[0.07]",
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
  warning:
    "border-[hsl(var(--tone-warning))]/45 bg-[hsl(var(--tone-warning))] text-white dark:text-background",
  info:
    "border-[hsl(var(--tone-info))]/45 bg-[hsl(var(--tone-info))] text-white dark:text-background",
  danger:
    "border-[hsl(var(--tone-danger))]/45 bg-[hsl(var(--tone-danger))] text-white dark:text-background",
  neutral: "border-border bg-muted text-foreground",
};

/**
 * The document's margin beside the paper, holding a block's count markers when it has
 * any. Wide enough for one marker; the paper starts after it and its gap.
 */
const RAIL_GRID = "grid-cols-[2.5rem_minmax(0,1fr)] gap-5";
const PAPER_OFFSET = "ml-[3.75rem]";
const PAPER_LEFT = "left-[3.75rem]";

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
          "inline-flex min-h-7 items-center gap-2 rounded-md border border-dashed px-2 py-1 text-left text-[11px] font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/60 motion-reduce:transition-none",
          "border-[hsl(var(--tone-warning))]/40 text-[hsl(var(--tone-warning))] hover:border-[hsl(var(--tone-warning))]/70 hover:bg-[hsl(var(--tone-warning))]/[0.06]",
          isActive && "border-[hsl(var(--tone-warning))] bg-[hsl(var(--tone-warning))]/10",
        )}
      >
        <CircleDashed aria-hidden="true" className="h-3.5 w-3.5 shrink-0" />
        <span>{label}</span>
        <span className="tabular-nums opacity-70">{annotations.length}</span>
      </button>
    </div>
  );
}

function BlockText<TKind extends string, TRef>({
  traceBlock,
  continuesTable,
  annotationsById,
  activeAnnotationIds,
  onSelect,
}: {
  traceBlock: DocumentTraceBlock<TKind, TRef>;
  /** A table row under the same headers as the row before it. */
  continuesTable: boolean;
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
    return <DocumentVisual block={traceBlock.block} />;
  }

  const presentation = documentBlockPresentation(traceBlock.block);

  if (presentation === "heading-primary") {
    return (
      <h2 className={cn(DISPLAY_HEADING, "m-0 text-balance text-xl font-semibold leading-tight text-foreground")}>
        {content}
      </h2>
    );
  }

  if (presentation === "heading-secondary") {
    return (
      <h3 className={cn(DISPLAY_HEADING, "m-0 text-balance text-lg font-semibold leading-tight text-foreground")}>
        {content}
      </h3>
    );
  }

  if (presentation === "heading-tertiary") {
    return (
      <h4 className={cn(DISPLAY_HEADING, "m-0 text-balance text-[15px] font-semibold leading-snug text-foreground")}>
        {content}
      </h4>
    );
  }

  if (presentation === "table-row") {
    const tableRow = documentTableCells(traceBlock.block);
    if (tableRow) {
      return (
        // Side by side when the columns fit and stacked when they do not: `.trace-table-row`
        // in globals.css, where the reason is written.
        <div className="trace-table-row border-l border-border/70 py-1 pl-4">
          <dl data-columns={tableRow.columnCount}>
            {tableRow.cells.map((cell) => {
              const headerSegments = documentTraceSegmentsInRange(
                traceBlock.segments,
                cell.contentStart,
                cell.headerEnd,
              );
              const valueSegments = documentTraceSegmentsInRange(
                traceBlock.segments,
                cell.valueStart,
                cell.valueEnd,
              );
              // In full on a table's first row; after it, the heading's own title line, enough
              // to name the column for a reader who arrives mid-table. Never shortened where a
              // result marks it.
              const brief = continuesTable
                && !headerSegments.some((segment) => segment.annotationIds.length > 0);
              return (
                <div
                  key={`${traceBlock.block.id}:cell:${cell.columnIndex}`}
                  className="min-w-0"
                  style={{ "--column": cell.columnIndex + 1 } as CSSProperties}
                >
                  {headerSegments.length > 0 && (
                    <dt
                      className={cn("mb-1 text-xs leading-5 text-muted-foreground", brief && "truncate")}
                      title={brief ? cell.header : undefined}
                    >
                      {brief ? tableHeaderLabel(cell.header) : (
                        <TraceSegmentText
                          blockId={traceBlock.block.id}
                          segments={headerSegments}
                          annotationsById={annotationsById}
                          activeAnnotationIds={activeAnnotationIds}
                          onSelect={onSelect}
                        />
                      )}
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
      <p className="m-0 whitespace-pre-wrap bg-foreground/[0.045] px-3 py-2 text-[13px] leading-5 tabular-nums text-foreground/85">
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
  closeAction,
}: {
  annotationIds: string[];
  annotationsById: Map<string, DocumentAnnotation<TKind, TRef>>;
  selectedId: string | null;
  connection: DocumentTraceConnection;
  onSelectId: (id: string) => void;
  passagesFor: (annotationId: string) => DocumentTracePassage[];
  onReveal: (blockId: string) => void;
  /** The panel's close control, placed on the first row this renders rather than in a bar of its own. */
  closeAction?: ReactNode;
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
  const sharedTitles = new Set(annotations
    .map((annotation) => annotation.title)
    .filter((title, index, titles) => titles.indexOf(title) !== index));

  if (!selected) {
    return (
      <div className="relative flex min-h-56 flex-col items-center justify-center px-6 text-center">
        {closeAction && <div className="absolute right-4 top-3.5">{closeAction}</div>}
        <FileText className="h-5 w-5 text-muted-foreground" aria-hidden="true" />
        <p className="mt-3 text-sm font-medium text-foreground">Select a marked passage</p>
        <p className="mt-1 max-w-56 text-xs leading-5 text-muted-foreground">
          The result that marks it opens here.
        </p>
      </div>
    );
  }

  return (
    <div>
      {annotations.length > 1 && (
        <>
          {/* Its own pinned row, a sibling of the list rather than inside it, so the close
              control it carries stays in reach however far the panel is scrolled. */}
          <div className={cn("flex items-center justify-between gap-3 px-4 pt-3 pb-2", closeAction && "sticky top-0 z-10 bg-card")}>
            <p className={EYEBROW}>
              Results <span className="tabular-nums">{annotations.length}</span>
            </p>
            {closeAction}
          </div>
          <div className="border-b border-border/60 px-4 pb-3">
            <div className="max-h-60 space-y-1 overflow-y-auto overscroll-contain pr-1">
              {annotations.map((annotation) => (
                <button
                  key={annotation.id}
                  type="button"
                  onClick={() => onSelectId(annotation.id)}
                  aria-pressed={annotation.id === selected.id}
                  aria-label={`View ${annotation.layerLabel}: ${annotation.title}`}
                  // The passage list's own row shape, so the open one is the only one boxed.
                  className={cn(
                    "grid min-h-10 w-full min-w-0 grid-cols-[6.5rem_minmax(0,1fr)] items-center gap-2 rounded-md border px-2 py-1.5 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/60 motion-reduce:transition-none",
                    annotation.id === selected.id
                      ? "border-border bg-foreground/[0.07] text-foreground"
                      : "border-transparent text-muted-foreground hover:border-border hover:bg-foreground/[0.045] hover:text-foreground",
                  )}
                >
                  <span className="truncate text-[11px] font-medium">
                    {annotation.layerLabel}
                  </span>
                  {/* The summary under the title only where titles repeat: results on one
                      passage often share one - every Aligner requirement of one comparison
                      does - and titles alone listed identical rows. Otherwise the panel
                      below says it, once. */}
                  <span className="min-w-0">
                    <span className="block truncate text-xs font-medium">{annotation.title}</span>
                    {sharedTitles.has(annotation.title) && annotation.summary && (annotation.summaryMode === "quoted" ? (
                      <span className="block truncate text-[11px] text-muted-foreground">{annotation.summary}</span>
                    ) : (
                      <Reading inline className="block truncate">{annotation.summary}</Reading>
                    ))}
                  </span>
                </button>
              ))}
            </div>
          </div>
        </>
      )}
      {/* The close control goes to the inspector's own heading only when no list above it
          has taken it. */}
      <TracePanelCloseProvider value={annotations.length > 1 ? null : closeAction}>
        {renderInspector(selected, connection, {
          passages: passagesFor(selected.id),
          reveal: onReveal,
        })}
      </TracePanelCloseProvider>
      {/* Here, once, for every tool: the panel is where a reader has the finding and its
          passages in front of them, which is the moment they can say it is wrong. */}
      <div className="border-t border-border/60 px-4 py-2">
        <ReportFinding
          report={{
            finding: `${selected.layerLabel}: ${selected.title}`,
            detail: selected.summary,
            reference: selected.id,
            location: passagesFor(selected.id)
              .map((passage) => [passage.documentId, passage.sectionLabel, compactBlockId(passage.blockId)].filter(Boolean).join(" · "))
              .join("; "),
          }}
        />
      </div>
    </div>
  );
}

export function DocumentTraceViewer<TKind extends string, TRef>({
  blocks,
  annotations,
  layers,
  defaultLayer,
  renderInspector,
  focus,
  onFocusConsumed,
}: DocumentTraceViewerProps<TKind, TRef>) {
  // The tool's preferred layer, unless nothing in it sits in the document. Inspector asks
  // for "Not present" first, and absence cites no passage by definition, so the document
  // opened with no mark anywhere on it. The next layer in the tool's own order that marks
  // something is shown instead; the reader can still choose the empty one.
  const [layer, setLayer] = useState<TKind | "all">(() => {
    const placed = (kind: TKind) => annotations.some((annotation) => annotation.kind === kind && annotation.blockIds.length > 0);
    if (!defaultLayer || placed(defaultLayer)) return defaultLayer ?? "all";
    return layers.find((option) => placed(option.value))?.value ?? defaultLayer;
  });
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
  // The two layout modes, not the width they come from: a width stored per pixel
  // re-rendered the whole trace on every frame of a resize for two values that change
  // at two thresholds.
  const [panelMode, setPanelMode] = useState(() => documentTracePanelMode(0));
  const [railMode, setRailMode] = useState(() => documentTraceRailMode(0));
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
  const surfaces = useMemo(
    () => groupDocumentTraceSurfaces(activeDocument?.blocks ?? []),
    [activeDocument],
  );
  const unresolvedAnnotations = trace.unresolvedAnnotationIds
    .map((id) => annotationsById.get(id))
    .filter((annotation): annotation is DocumentAnnotation<TKind, TRef> => Boolean(annotation));
  const unplacedAnnotations = trace.unplacedAnnotationIds
    .map((id) => annotationsById.get(id))
    .filter((annotation): annotation is DocumentAnnotation<TKind, TRef> => Boolean(annotation));
  // "Does the panel fit beside the document" — decided by the two columns' own widths,
  // not by a viewport breakpoint no page's container can clear. See the helper.
  const isNarrow = panelMode === "sheet";

  /**
   * Show one passage: switch document if it lives in another one, scroll it to the
   * middle, and ring it. Nothing else.
   *
   * One path for both callers — a result row handing in a `focus`, and the panel's
   * own passage list — because they are the same act, and two paths meant one click
   * behaved differently depending on where it came from.
   *
   * It deliberately selects nothing. Opening the details panel on arrival put a reader
   * in front of a panel restating the row they had just left, and on a narrow container
   * that panel is a sheet covering the passage it was sent to reveal. Arrival centres
   * the block; opening its result stays a second, deliberate click on the mark.
   */
  useEffect(() => {
    const blockId = focus?.blockId ?? revealBlockId;
    if (!blockId) return;
    const done = () => {
      if (focus) onFocusConsumed?.(focus);
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
      // The layer the reader asked for, when they asked for one. A click on a specific
      // result names it, and opening on every layer there would answer a question they
      // did not ask: a passage cited by six findings would show all six when they
      // clicked one. Falling back to the block's own kinds keeps triggers that name no
      // result - a section card, a priority row - behaving as they did.
      const requested = focus?.annotationId
        ? allAnnotationsById.get(focus.annotationId)?.kind
        : undefined;
      const kinds = new Set(
        requested
          ? [requested]
          : location.annotationIds
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
    // Open supporting text before measuring its position, without selecting a result.
    target.closest<HTMLDetailsElement>("details[data-source-text]")?.setAttribute("open", "");
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
    focus,
    fullTrace,
    layer,
    layers,
    onFocusConsumed,
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
    const update = (width: number) => {
      setPanelMode(documentTracePanelMode(width));
      setRailMode(documentTraceRailMode(width));
    };
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
    // Opening the side panel narrows the text column by its width, so the text reflows
    // and the passage just clicked can move out of view. Once the new layout has painted,
    // bring it back - only if it left the view, so a click on a visible mark moves nothing.
    const opensPanel = !isNarrow && selectedAnnotationId === null;
    setActiveAnnotationIds(availableIds);
    setSelectedAnnotationId(availableIds[0]);
    setConnection(nextConnection);
    if (opensPanel) {
      window.requestAnimationFrame(() => window.requestAnimationFrame(() => {
        const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        trigger.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "nearest" });
      }));
    }
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
    <div ref={rootRef} className="bg-foreground/[0.045]">
      <div className={cn(
        "flex gap-3 border-b border-border/60 bg-card px-5 py-3 sm:px-6",
        isNarrow ? "flex-col" : "items-center",
      )}>
        {/* The document shown, named by its picker when there are several, and how many
            results the chosen layer marks. The tab already says this is the documents view. */}
        <div className="flex min-w-0 flex-1 items-center gap-2">
          {trace.documents.length > 1 ? (
            <Select value={activeDocumentId} onValueChange={setDocumentId}>
              <SelectTrigger className={cn("h-8 bg-card text-xs", isNarrow ? "w-full" : "w-60")} aria-label="Source document" title={displayDocumentName(activeDocumentId)}>
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
          ) : (
            <>
              <FileText className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
              <p className="min-w-0 truncate text-xs font-medium text-foreground" title={displayDocumentName(activeDocumentId)}>
                {displayDocumentName(activeDocumentId)}
              </p>
            </>
          )}
          <span className="shrink-0 text-[11px] tabular-nums text-muted-foreground" role="status">
            {countLabel(visibleAnnotations.length, "result")}
          </span>
        </div>
        <div className={cn("flex gap-2", isNarrow ? "flex-col" : "flex-row")}>
          <Select value={layer} onValueChange={(value) => setLayer(value as TKind | "all")}>
            <SelectTrigger className={cn("h-8 bg-card text-xs", isNarrow ? "w-full" : "w-52")} aria-label="Trace layer">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All results</SelectItem>
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
        <details className="border-b border-border/60 bg-card px-5 py-3 sm:px-6">
          <DisclosureSummary className="w-fit rounded-sm text-xs font-medium text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/60">
            Citing passages not in this file <span className={COUNT}>{unresolvedAnnotations.length}</span>
          </DisclosureSummary>
          <p className="mt-2 max-w-2xl text-xs leading-5 text-muted-foreground">
            These results cite passages the saved file does not hold, so they cannot be marked in the text. Each still opens.
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
                className="min-h-8 rounded-md border border-border/80 bg-background px-2.5 py-1 text-left text-[11px] font-medium text-muted-foreground transition-colors hover:border-foreground/20 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/60 motion-reduce:transition-none"
              >
                {annotation.layerLabel} · {annotation.title}
              </button>
            ))}
          </div>
        </details>
      )}

      {unplacedAnnotations.length > 0 && (
        <details className="border-b border-border/60 bg-card px-5 py-3 sm:px-6">
          <DisclosureSummary className="w-fit rounded-sm text-xs font-medium text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/60">
            Not located in this document <span className={COUNT}>{unplacedAnnotations.length}</span>
          </DisclosureSummary>
          <p className="mt-2 max-w-2xl text-xs leading-5 text-muted-foreground">
            These results describe content the document lacks, so they cite no passage to mark.
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
                className="min-h-8 rounded-md border border-border/80 bg-background px-2.5 py-1 text-left text-[11px] font-medium text-muted-foreground transition-colors hover:border-foreground/20 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/60 motion-reduce:transition-none"
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
            "max-h-[min(76vh,58rem)] overflow-y-auto overscroll-contain bg-foreground/[0.045] py-6",
            isNarrow ? "px-3 sm:px-6" : "px-8",
          )}
        >
          <article
            aria-label={`Reconstructed source document: ${displayDocumentName(activeDocumentId)}`}
            className={cn(
              "relative mx-auto min-h-full space-y-8",
              railMode === "inline"
                ? "max-w-[52rem]"
                : "max-w-[60rem]",
            )}
          >
            {surfaces.map((surface) => (
              <section
                key={surface.key}
                data-trace-surface={surface.key}
                aria-label={surface.boundary?.label}
                className={cn(
                  "relative",
                  railMode === "inline"
                    ? "rounded-lg bg-card px-5 py-8 shadow-raised sm:px-10 sm:py-12"
                    : "py-12",
                )}
              >
                {railMode === "external" && (
                  <div
                    aria-hidden="true"
                    className={cn("pointer-events-none absolute inset-y-0 right-0 rounded-lg bg-card shadow-raised", PAPER_LEFT)}
                  />
                )}
                {surface.boundary && (
                  <p className={cn(
                    "relative z-10 pb-6 text-xs font-medium text-muted-foreground",
                    railMode === "external" && cn(PAPER_OFFSET, "px-10"),
                  )}>
                    {surface.boundary.label}
                  </p>
                )}
                <SourceSurfaceContent blocks={surface.blocks} externalRail={railMode === "external"}>
                {surface.blocks.map((traceBlock, blockIndex) => {
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
                  // Counts appear only for connections with no visible mark in the paper.
                  // When the block itself is marked, the mark is the target and a second
                  // control here would duplicate it.
                  const showsMarkers = !blockIsMarkTarget && markerGroups.length > 0;
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
                          : RAIL_GRID,
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
                      {/* The margin keeps its grid cell while empty; inline, an empty row
                          would only add space above the block. */}
                      {(railMode === "external" || showsMarkers) && <div className={cn(
                        "relative z-10 flex min-w-0 flex-row flex-wrap items-center gap-1",
                        railMode === "inline"
                          ? "mb-2"
                          : "justify-end self-start pt-1",
                      )}>
                        {showsMarkers && markerGroups.map((group) => {
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
                                "inline-flex h-6 min-w-6 items-center justify-center gap-1 rounded-md border border-border/70 bg-background px-1.5 text-[10px] font-medium text-muted-foreground transition-colors hover:border-foreground/20 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/60 motion-reduce:transition-none",
                                isActive && "border-foreground/25 bg-foreground text-background",
                              )}
                              title={label}
                            >
                              <Link2 aria-hidden="true" className="h-3 w-3 shrink-0" />
                              <span className="tabular-nums">{group.annotationIds.length}</span>
                            </button>
                          );
                        })}
                      </div>}
                      <div
                        className={cn(
                          "relative z-10 min-w-0 rounded-md transition-[background-color,box-shadow] duration-slow motion-reduce:transition-none",
                          railMode === "external" && "px-10 py-1",
                          emphasisVisible
                            && traceBlock.emphasis
                            && EMPHASIS_SURFACE_CLASS[traceBlock.emphasis.tone],
                          "group-hover/trace-block:bg-foreground/[0.045] group-focus-within/trace-block:bg-foreground/[0.045]",
                          blockIsMarkTarget
                            && "cursor-pointer hover:bg-[hsl(var(--tone-marked))]/10 focus-within:bg-[hsl(var(--tone-marked))]/10",
                        )}
                        onClick={blockIsMarkTarget ? (event) => {
                          // Selecting text inside a marked block must not open its
                          // detail, or the passage becomes impossible to quote.
                          if (!window.getSelection()?.isCollapsed) return;
                          const badge = event.currentTarget.querySelector("[data-trace-mark-action]");
                          if (badge instanceof HTMLElement) badge.click();
                        } : undefined}
                      >
                        <BlockText
                          traceBlock={traceBlock}
                          continuesTable={documentTableRowContinues(surface.blocks[blockIndex - 1]?.block, traceBlock.block)}
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
                            data-trace-mark-action
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
                              "absolute bottom-1.5 right-2 z-10 inline-flex h-5 min-w-5 items-center justify-center rounded border px-1 text-[10px] font-semibold tabular-nums transition-opacity duration-base focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/60 motion-reduce:transition-none",
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
                </SourceSurfaceContent>
              </section>
            ))}
            {activeDocument && visibleAnnotations.length === 0 && (
              <p className="mt-8 rounded-md bg-foreground/[0.045] px-4 py-3 text-center text-xs leading-5 text-muted-foreground">
                No result in this layer marks a passage.
              </p>
            )}
          </article>
        </div>

        {!isNarrow && selectedAnnotationId && (
          <aside className="border-l border-border/60 bg-card" aria-label="Details">
            <div className="sticky top-0 max-h-[min(76vh,58rem)] overflow-y-auto overscroll-contain">
              <AnnotationInspector
                closeAction={(
                  <button
                    type="button"
                    onClick={closeInspector}
                    aria-label="Close details"
                    // Pulled out by its own padding so the × sits on the heading's edge and
                    // centre rather than pushing the row taller.
                    className="-my-1.5 -mr-2 inline-flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-foreground/[0.045] hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/60 motion-reduce:transition-none"
                  >
                    <X className="h-4 w-4" aria-hidden="true" />
                  </button>
                )}
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
            aria-label="Close details"
          />
          <div
            ref={sheetRef}
            role="dialog"
            aria-modal="true"
            aria-label="Details"
            className="absolute inset-x-3 bottom-3 max-h-[min(76vh,42rem)] overflow-y-auto overscroll-contain rounded-2xl bg-card shadow-overlay"
          >
            <TracePanelHeader
              title="Details"
              className="sticky top-0 z-10 bg-card/95 backdrop-blur"
              action={(
                <button
                  ref={closeButtonRef}
                  type="button"
                  onClick={closeInspector}
                  className="inline-flex h-9 w-9 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-foreground/[0.045] hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/60 motion-reduce:transition-none"
                  aria-label="Close details"
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
