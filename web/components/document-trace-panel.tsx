"use client";

import { useState } from "react";
import { ArrowRight, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import {
  displayDocumentName,
  type DocumentTracePassage,
} from "@/lib/document-trace";
import { cn } from "@/lib/utils";

export function TracePanelHeader({
  eyebrow,
  title,
  description,
  action,
  className,
}: {
  eyebrow: string;
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <header className={cn("border-b border-border/80 px-4 py-3.5", className)}>
      <div className="flex min-w-0 items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
            {eyebrow}
          </p>
          <h3 className="mt-1 text-balance text-sm font-semibold leading-tight text-foreground">
            {title}
          </h3>
        </div>
        {action && <div className="shrink-0">{action}</div>}
      </div>
      {description && (
        <div className="mt-1.5 text-[11px] leading-relaxed text-muted-foreground">
          {description}
        </div>
      )}
    </header>
  );
}

export function TracePanelSection({
  label,
  icon: Icon,
  children,
  className,
}: {
  label: string;
  icon?: LucideIcon;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("border-t border-border/70 pt-4", className)}>
      <div className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.1em] text-muted-foreground">
        {Icon && <Icon className="h-3.5 w-3.5" aria-hidden="true" />}
        {label}
      </div>
      {children}
    </section>
  );
}

/**
 * Every passage a result was read from, each one openable.
 *
 * This replaced a bare count. A result citing four passages showed "4 source
 * passages" and put you at one of them, so the other three were asserted and
 * unreachable — the count told you evidence existed without letting you check it,
 * which is the opposite of what a trace is for.
 *
 * Shared by every tool's inspector rather than written into each, because "which
 * passages, and take me there" is the same question whatever the result claims; only
 * the prose above it differs by tool.
 */
export function TracePassageList({
  passages,
  openedBlockId,
  onReveal,
  className,
}: {
  passages: DocumentTracePassage[];
  /** The passage the panel was opened from, marked so a reader keeps their place. */
  openedBlockId?: string;
  onReveal: (blockId: string) => void;
  className?: string;
}) {
  const [revealedBlockId, setRevealedBlockId] = useState<string | null>(null);
  if (!passages.length) return null;

  // Named only when it disambiguates. A result can cite two uploaded documents, and
  // repeating one document's name down a list that never leaves it is noise.
  const spansDocuments = new Set(passages.map((passage) => passage.documentId)).size > 1;
  // Guarded against a stale click: the panel keeps this component mounted when the
  // selected result changes, and the last passage opened may belong to the old one.
  const marked = passages.some((passage) => passage.blockId === revealedBlockId)
    ? revealedBlockId
    : openedBlockId;

  return (
    <ol className={cn("mt-3 space-y-1", className)}>
      {passages.map((passage, index) => {
        const isMarked = passage.blockId === marked;
        return (
          <li key={passage.blockId}>
            <button
              type="button"
              onClick={() => {
                setRevealedBlockId(passage.blockId);
                onReveal(passage.blockId);
              }}
              aria-current={isMarked ? "true" : undefined}
              aria-label={`Show passage ${index + 1} of ${passages.length} in the document${
                spansDocuments ? `, ${displayDocumentName(passage.documentId)}` : ""
              }${passage.sectionLabel ? `, ${passage.sectionLabel}` : ""}`}
              className={cn(
                "group/passage grid w-full min-w-0 grid-cols-[1.25rem_minmax(0,1fr)_0.875rem] items-start gap-2 rounded-md border px-2 py-1.5 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/30 motion-reduce:transition-none",
                isMarked
                  ? "border-border bg-muted/70"
                  : "border-transparent hover:border-border hover:bg-muted/40",
              )}
            >
              <span className="pt-px text-[10px] tabular-nums text-muted-foreground">
                {index + 1}
              </span>
              <span className="min-w-0">
                {(spansDocuments || passage.sectionLabel) && (
                  <span className="block truncate text-[10px] font-medium uppercase tracking-[0.08em] text-muted-foreground">
                    {[
                      spansDocuments ? displayDocumentName(passage.documentId) : "",
                      passage.sectionLabel,
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </span>
                )}
                <span className="mt-0.5 block text-[11px] leading-4 text-foreground">
                  {passage.preview}
                </span>
              </span>
              <ArrowRight
                className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground/0 transition-colors group-hover/passage:text-muted-foreground motion-reduce:transition-none"
                aria-hidden="true"
              />
            </button>
          </li>
        );
      })}
    </ol>
  );
}
