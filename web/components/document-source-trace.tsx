"use client";

import {
  createContext,
  type ReactNode,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { Check, Copy, FileText, LocateFixed } from "lucide-react";
import { BlockReferenceId } from "@/components/block-reference";
import { TracePanelHeader, TracePanelSection } from "@/components/document-trace-panel";
import type { ContentBlock } from "@/lib/api";
import { sourcePassageAriaLabel } from "@/lib/block-reference";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";

export type DocumentSpan = { quote: string; block_ids: string[] };

type DocumentSourceContextValue = {
  blocks: ContentBlock[];
  onOpenInTrace?: (blockId: string) => void;
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
  onOpenInTrace?: (blockId: string) => void;
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
}: {
  blockIds?: string[];
  spans?: DocumentSpan[];
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
  const selectedHeading = selectedBlock
    ? selectedBlock.section_label ||
      selectedBlock.heading_stack[selectedBlock.heading_stack.length - 1] ||
      "Source passage"
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
        <button
          type="button"
          onClick={(event) => event.stopPropagation()}
          onPointerDown={(event) => event.stopPropagation()}
          className="inline-flex h-7 shrink-0 items-center gap-1.5 rounded-md border border-transparent px-2 text-[10px] font-medium text-muted-foreground transition-colors hover:border-border hover:bg-muted/60 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/20 motion-reduce:transition-none"
          aria-label={sourcePassageAriaLabel(uniqueBlockIds.length)}
        >
          <FileText className="h-3 w-3" />
          View source
          {uniqueBlockIds.length > 1 && (
            <span className="tabular-nums text-muted-foreground/70">{uniqueBlockIds.length}</span>
          )}
        </button>
      </PopoverTrigger>
      <PopoverContent
        align="end"
        sideOffset={6}
        collisionPadding={12}
        className="w-[min(720px,calc(100vw-24px))] overflow-hidden p-0"
      >
        <TracePanelHeader
          eyebrow="Source passage"
          title="Uploaded document"
          description="Read the retained passage behind this result, then open its exact location in the document trace."
        />
        <div className={uniqueBlockIds.length > 1 ? "grid min-h-0 sm:grid-cols-[180px_minmax(0,1fr)]" : "min-h-0"}>
          {uniqueBlockIds.length > 1 && (
            <nav
              aria-label="Source passages"
              className="flex max-h-32 gap-1 overflow-auto border-b border-border/80 bg-muted/15 p-2 sm:max-h-[min(58vh,520px)] sm:flex-col sm:border-b-0 sm:border-r"
            >
              {uniqueBlockIds.map((blockId, index) => {
                const block = blocksById.get(blockId);
                const label = block?.section_label ||
                  block?.heading_stack[block.heading_stack.length - 1] ||
                  `Passage ${index + 1}`;
                return (
                  <button
                    key={blockId}
                    type="button"
                    onClick={() => setSelectedBlockId(blockId)}
                    className={`min-w-32 rounded-md px-2.5 py-2 text-left outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring/20 sm:min-w-0 ${
                      selectedBlockId === blockId
                        ? "bg-card text-foreground shadow-sm ring-1 ring-border"
                        : "text-muted-foreground hover:bg-muted/60 hover:text-foreground"
                    }`}
                  >
                    <span className="block text-[9px] font-medium uppercase tracking-wide text-muted-foreground/70">
                      Passage {index + 1}
                    </span>
                    <span className="mt-0.5 block truncate text-[11px] font-medium">{label}</span>
                  </button>
                );
              })}
            </nav>
          )}
          <article className="max-h-[min(58vh,520px)] min-w-0 overflow-y-auto px-4 py-4">
            {selectedBlock ? (
              <>
                <div className="min-w-0">
                  <p className="truncate text-xs font-semibold text-foreground">{selectedHeading}</p>
                  <p className="mt-0.5 text-[10px] capitalize text-muted-foreground">
                    {selectedBlock.block_type.replaceAll("_", " ")} · passage {selectedBlock.ordinal + 1}
                  </p>
                </div>
                {selectedQuotes.length > 0 && (
                  <TracePanelSection
                    label="Exact cited text"
                    icon={FileText}
                    className="mt-3 rounded-lg border border-border/80 bg-muted/20 px-3.5 py-3"
                  >
                    <div className="mt-1.5 space-y-2">
                      {selectedQuotes.map((quote) => (
                        <blockquote key={quote} className="border-l-2 border-foreground/30 pl-3 text-xs leading-relaxed text-foreground">
                          {quote}
                        </blockquote>
                      ))}
                    </div>
                  </TracePanelSection>
                )}
                {selectedBlock.image && (
                  <div className="mt-3 overflow-hidden rounded-lg border border-border/80 bg-muted/20 p-2">
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
                    <p className="text-[9px] font-medium uppercase tracking-wide text-muted-foreground">
                      Surrounding passage
                    </p>
                    <p className="mt-1.5 whitespace-pre-wrap break-words text-xs leading-6 text-foreground/85">
                      {selectedBlock.content}
                    </p>
                  </section>
                )}
              </>
            ) : (
              <div className="rounded-lg border border-dashed border-border px-4 py-8 text-center">
                <p className="text-xs font-medium text-foreground">Source passage unavailable</p>
                <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">
                  This imported result references the passage but does not retain its source content.
                </p>
              </div>
            )}
            <footer className="mt-4 flex flex-wrap items-center gap-2 border-t border-border/70 pt-3">
              <span className="text-[9px] font-medium uppercase tracking-wide text-muted-foreground">Block ID</span>
              <BlockReferenceId
                blockId={selectedBlockId}
                className="min-w-0 flex-1 truncate text-[9px] text-muted-foreground"
              />
              <button
                type="button"
                onClick={() => void copyBlockId(selectedBlockId)}
                aria-label={`Copy block ID ${selectedBlockId}`}
                className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-muted-foreground outline-none transition-colors hover:bg-muted hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/20 motion-reduce:transition-none"
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
                    window.requestAnimationFrame(() => onOpenInTrace(selectedBlockId));
                  }}
                  className="inline-flex min-h-7 items-center gap-1.5 rounded-md border border-border/80 bg-background px-2.5 text-[10px] font-medium text-foreground outline-none transition-colors hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring/20 motion-reduce:transition-none"
                >
                  <LocateFixed className="h-3.5 w-3.5" aria-hidden="true" />
                  Open in document trace
                </button>
              )}
            </footer>
          </article>
        </div>
      </PopoverContent>
    </Popover>
  );
}
