"use client";

import {
  createContext,
  type ReactNode,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { Check, Copy, FileText, LocateFixed, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { BlockReferenceId } from "@/components/block-reference";
import { TracePanelHeader } from "@/components/document-trace-panel";
import type { ContentBlock, DocumentSpan } from "@/lib/api";
import { sourcePassageAriaLabel } from "@/lib/block-reference";
import { documentBlockLocationLabel } from "@/lib/document-extraction";
import { CitedMark, Quoted } from "@/components/ui/evidence-text";
import { markCitedText } from "@/lib/cited-text";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { ProvenanceTrigger, stopRowToggle , PROVENANCE_PANEL} from "@/components/ui/provenance";
import type { TraceFocus } from "@/lib/trace-focus";
import { EmptyState } from "@/components/empty-state";
import { EYEBROW } from "@/lib/typography";
import { cn } from "@/lib/utils";

type DocumentSourceContextValue = {
  blocks: ContentBlock[];
  onOpenInTrace?: (focus: TraceFocus) => void;
};

/** Exported so any surface resolving a block ID resolves it the same way. */
export const DocumentSourceContext = createContext<DocumentSourceContextValue>({
  blocks: [],
});

export function DocumentSourceProvider({
  blocks,
  children,
  onOpenInTrace,
}: {
  blocks: ContentBlock[];
  children: ReactNode;
  onOpenInTrace?: (focus: TraceFocus) => void;
}) {
  return (
    <DocumentSourceContext.Provider value={{ blocks, onOpenInTrace }}>
      {children}
    </DocumentSourceContext.Provider>
  );
}

export function DocumentSourceTrace({
  blockIds,
  spans = [],
  annotationId,
}: {
  blockIds?: string[];
  spans?: DocumentSpan[];
  /**
   * The result this trigger belongs to, when it belongs to one.
   *
   * Carried so the trace can open on that result's own layer. Without it a passage
   * cited by six findings opens showing all of them, which is correct for a trigger
   * that names no finding and wrong for one that does.
   */
  annotationId?: string;
}) {
  const { blocks, onOpenInTrace } = useContext(DocumentSourceContext);
  const [open, setOpen] = useState(false);
  const [copiedBlockId, setCopiedBlockId] = useState<string | null>(null);
  const uniqueBlockIds = useMemo(
    () => Array.from(new Set(blockIds ?? [])),
    [blockIds],
  );
  const [selectedBlockId, setSelectedBlockId] = useState(uniqueBlockIds[0] ?? "");

  useEffect(() => {
    if (!uniqueBlockIds.includes(selectedBlockId)) {
      setSelectedBlockId(uniqueBlockIds[0] ?? "");
    }
  }, [selectedBlockId, uniqueBlockIds]);

  if (!uniqueBlockIds.length) return null;

  const blocksById = new Map(blocks.map((block) => [block.id, block]));
  const selectedBlock = blocksById.get(selectedBlockId) ?? null;
  const selectedQuotes = Array.from(new Set(
    spans
      .filter((span) => span.block_ids.includes(selectedBlockId))
      .map((span) => span.quote.trim())
      .filter(Boolean),
  ));
  // Matched on normalised whitespace, because on a real run 15 of 36 quotes differed from
  // their block only in spacing - a table row the parse renders with its own line breaks.
  const citedPassage = markCitedText(selectedBlock?.content ?? "", selectedQuotes);
  const selectedHeading = selectedBlock
    ? documentBlockLocationLabel(selectedBlock) || "Source passage"
    : "Source passage unavailable";

  async function copyBlockId(blockId: string) {
    try {
      await navigator.clipboard.writeText(blockId);
      setCopiedBlockId(blockId);
      window.setTimeout(() => setCopiedBlockId(null), 1400);
    } catch {
      setCopiedBlockId(null);
    }
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button type="button" aria-label={sourcePassageAriaLabel(uniqueBlockIds.length)} {...stopRowToggle}>
          <ProvenanceTrigger
            icon={FileText}
            label="In document"
            count={uniqueBlockIds.length}
            ariaLabel={sourcePassageAriaLabel(uniqueBlockIds.length)}
          />
        </button>
      </PopoverTrigger>
      <PopoverContent
        align="start"
        sideOffset={6}
        collisionPadding={12}
        className={cn(PROVENANCE_PANEL.width, "overscroll-contain p-0")}
      >
        <TracePanelHeader
          eyebrow="Source passage"
          className="sticky top-0 z-10 bg-card"
          title="Uploaded document"
          description="Passages cited by this result."
          action={<Button type="button" variant="ghost" size="icon" className="h-8 w-8" aria-label="Close source passages" onClick={() => setOpen(false)}><X className="h-4 w-4" aria-hidden="true" /></Button>}
        />
        <div className={uniqueBlockIds.length > 1 ? "grid min-h-0 sm:grid-cols-[180px_minmax(0,1fr)]" : "min-h-0"}>
          {uniqueBlockIds.length > 1 && (
            // The surface stretches with the grid row; only the list is height-capped.
            // Capping the surface itself left the divider and background cut short
            // whenever the selected passage was taller than the navigation.
            <div className="min-w-0 border-b border-border/80 bg-foreground/[0.045] sm:border-b-0 sm:border-r">
            <nav
              aria-label="Source passages"
              className="flex max-h-32 gap-1 overflow-auto overscroll-contain p-2 sm:max-h-72 sm:flex-col"
            >
              {uniqueBlockIds.map((blockId, index) => {
                const block = blocksById.get(blockId);
                const label = (block && documentBlockLocationLabel(block)) || `Passage ${index + 1}`;
                return (
                  <button
                    key={blockId}
                    type="button"
                    onClick={() => setSelectedBlockId(blockId)}
                    aria-current={selectedBlockId === blockId ? "true" : undefined}
                    className={`min-w-32 rounded-md px-2.5 py-2 text-left outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring/20 sm:min-w-0 ${
                      selectedBlockId === blockId
                        ? "bg-card text-foreground shadow-sm ring-1 ring-border"
                        : "text-muted-foreground hover:bg-foreground/[0.045] hover:text-foreground"
                    }`}
                  >
                    <span className={cn("block", EYEBROW)}>
                      Passage {index + 1}
                    </span>
                    <span className="mt-0.5 block truncate text-[11px] font-medium">{label}</span>
                    <span className="mt-1 line-clamp-2 text-xs leading-relaxed text-muted-foreground">
                      {block?.content || (block?.image ? "Image passage" : "Source passage unavailable")}
                    </span>
                  </button>
                );
              })}
            </nav>
            </div>
          )}
          {/* The same scroll box as its three sibling panels. It was 58vh where they were 60,
                a difference of two viewport percent that marked nothing. */}
          <article className={cn(PROVENANCE_PANEL.scroll, "min-w-0 overflow-y-auto px-4 py-4")}>
            {selectedBlock ? (
              <>
                <div className="min-w-0">
                  <p className="break-words text-xs font-semibold text-foreground">{selectedHeading}</p>
                  <p className="mt-0.5 text-[10px] capitalize text-muted-foreground">
                    {selectedBlock.block_type.replaceAll("_", " ")} · passage {selectedBlock.ordinal + 1}
                  </p>
                </div>
                {selectedBlock.image && (
                  <div className="mt-3 overflow-hidden rounded-lg border border-border/80 bg-foreground/[0.045] p-2">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={`data:${selectedBlock.image.media_type};base64,${selectedBlock.image.data_base64}`}
                      alt={`Visual from ${selectedHeading}`}
                      className="mx-auto max-h-72 max-w-full object-contain"
                    />
                  </div>
                )}
                {selectedBlock.content && (
                  <section className="mt-3">
                    <p className={EYEBROW}>
                      Passage
                    </p>
                    {/* The cited words marked where they sit, not repeated above. Showing them
                        in their own box and again inside the passage was the same sentence
                        twice, and left the reader matching two strings to find which part of
                        the passage was actually cited. */}
                    <p className="mt-1.5 whitespace-pre-wrap break-words text-xs leading-6 text-foreground">
                      {citedPassage.segments.map((segment, index) =>
                        segment.cited ? (
                          <CitedMark key={index}>{segment.text}</CitedMark>
                        ) : (
                          <span key={index}>{segment.text}</span>
                        ),
                      )}
                    </p>
                    {/* A quote the passage does not contain is shown rather than lost. With
                        the separate box gone this is the only thing standing between an
                        unlocatable citation and it vanishing. */}
                    {citedPassage.unplaced.length > 0 && (
                      <div className="mt-2.5">
                        <p className={EYEBROW}>
                          Cited text not found in this passage
                        </p>
                        {citedPassage.unplaced.map((quote) => (
                          <Quoted key={quote}>{quote}</Quoted>
                        ))}
                      </div>
                    )}
                  </section>
                )}
              </>
            ) : (
              <EmptyState
                message="Source passage unavailable"
                detail="This imported result references the passage but does not retain its source content."
              />
            )}
            <footer className="mt-4 flex flex-wrap items-center gap-2 border-t border-border/70 pt-3">
              <span className={EYEBROW}>Block ID</span>
              <BlockReferenceId
                blockId={selectedBlockId}
                className="min-w-0 flex-1 truncate text-[10px] text-muted-foreground"
              />
              <button
                type="button"
                onClick={() => void copyBlockId(selectedBlockId)}
                aria-label={`Copy block ID ${selectedBlockId}`}
                className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-muted-foreground outline-none transition-colors hover:bg-foreground/[0.045] hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/20 motion-reduce:transition-none"
              >
                {copiedBlockId === selectedBlockId
                  ? <Check className="h-3.5 w-3.5" />
                  : <Copy className="h-3.5 w-3.5" />}
              </button>
              {onOpenInTrace && selectedBlock && (
                <button
                  type="button"
                  onClick={() => {
                    setOpen(false);
                    window.requestAnimationFrame(() =>
                      onOpenInTrace({ blockId: selectedBlockId, annotationId }),
                    );
                  }}
                  className="inline-flex min-h-7 items-center gap-1.5 rounded-md border border-border/80 bg-background px-2.5 text-[10px] font-medium text-foreground outline-none transition-colors hover:bg-foreground/[0.045] focus-visible:ring-2 focus-visible:ring-ring/20 motion-reduce:transition-none"
                >
                  <LocateFixed className="h-3.5 w-3.5" aria-hidden="true" />
                  View in document
                </button>
              )}
            </footer>
          </article>
        </div>
      </PopoverContent>
    </Popover>
  );
}
