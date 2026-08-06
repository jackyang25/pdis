"use client";

import { useState } from "react";
import { ChevronUp } from "lucide-react";

import { DocumentSourceTrace } from "@/components/document-source-trace";
import { cn } from "@/lib/utils";

/**
 * The panel a tool opens with: what to look at first, in one shape everywhere.
 *
 * This component owns the container and nothing else. It does not decide what is a
 * priority, in what order, or why - a tool passes items already selected and already
 * ordered. That split is the point: changing what counts as a priority means editing
 * one selector in `lib`, and no part of this file, any page, or any other tool moves.
 *
 * Two ways to improve a tool's priorities without touching the container:
 *   1. change the selector - what qualifies and how it ranks
 *   2. change what you hand the selector - which results it may consider
 *
 * The sparkle is honest here and would not be on a summary of counts: every
 * `statement` below is model-written prose. What is *not* the model's is the order,
 * so `orderNote` states the rule rather than letting the glyph imply the ranking was
 * a judgment too.
 */

/**
 * One thing worth looking at, in the shape every tool maps into.
 *
 * Deliberately small. A field here has to make sense for a rubric gap, a
 * contradicted target, and whatever the next tool produces - anything narrower
 * belongs in the tool's own view, not in the panel every tool shares.
 */
export type PriorityItem = {
  /** Stable across renders; the tool's own identifier for the thing. */
  id: string;
  /** The subject, in bold: a rubric unit, a variable, a target. */
  label: string;
  /** Muted trail after the label: where it sits, and why it was raised. */
  qualifier?: string;
  /** What is the matter, in the tool's own words. */
  statement: string;
  /** What to do about it, when the tool has something to say. */
  recommendation?: string;
  /** Source passages behind it, rendered as the shared document trace. */
  blockIds?: string[];
};

export function PriorityPanel({
  attribution,
  items,
  emptyMessage,
  orderNote,
  title = "Priorities",
  defaultOpen = true,
}: {
  /** Who produced the wording, e.g. "by Inspector". */
  attribution: string;
  items: PriorityItem[];
  /** Shown instead of the list when there is nothing to raise. */
  emptyMessage: string;
  /** How the order was decided. Stated because the sparkle does not cover it. */
  orderNote: string;
  title?: string;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <section className="rounded-lg border border-border">
      <div className="flex flex-wrap items-center gap-3 px-5 py-[14px] sm:px-6">
        <p className="flex min-w-0 flex-1 items-center gap-2 text-sm">
          <PriorityGlyph />
          <span className="font-semibold text-foreground">{title}</span>
          <span className="truncate text-muted-foreground">
            {items.length > 0 ? `${items.length} ${attribution}` : attribution}
          </span>
        </p>
        <button
          type="button"
          onClick={() => setOpen((current) => !current)}
          aria-expanded={open}
          aria-label={open ? `Hide ${title.toLowerCase()}` : `Show ${title.toLowerCase()}`}
          className="shrink-0 rounded-md p-1 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/20 motion-reduce:transition-none"
        >
          <ChevronUp
            className={cn(
              "h-4 w-4 transition-transform duration-base motion-reduce:transition-none",
              !open && "rotate-180",
            )}
          />
        </button>
      </div>
      {open && (
        <div className="border-t border-border px-5 py-4 sm:px-6">
          {items.length > 0 ? (
            <ul className="space-y-3">
              {items.map((item) => (
                <li key={item.id} className="flex gap-2.5 text-sm leading-6">
                  <span aria-hidden className="select-none text-muted-foreground">
                    •
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="flex flex-wrap items-baseline gap-x-1.5">
                      <span className="font-medium">{item.label}</span>
                      {item.qualifier && (
                        <span className="text-xs text-muted-foreground">
                          {item.qualifier}
                        </span>
                      )}
                    </p>
                    <p className="mt-0.5">{item.statement}</p>
                    {item.recommendation && (
                      <p className="mt-0.5 text-muted-foreground">
                        {item.recommendation}
                      </p>
                    )}
                    {item.blockIds && item.blockIds.length > 0 && (
                      <div className="mt-1.5">
                        <DocumentSourceTrace blockIds={item.blockIds} />
                      </div>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">{emptyMessage}</p>
          )}
          <p className="mt-4 border-t border-border pt-2.5 text-xs leading-5 text-muted-foreground">
            {orderNote}
          </p>
        </div>
      )}
    </section>
  );
}

/**
 * The one glyph, declared here so both tools cannot drift apart on it.
 *
 * `lucide-react`'s Sparkles, inlined rather than imported per page so the marker for
 * "a model wrote this" has exactly one definition.
 */
function PriorityGlyph() {
  return (
    <svg
      aria-hidden
      viewBox="0 0 24 24"
      className="h-4 w-4 shrink-0 fill-none stroke-current stroke-2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3Z" />
      <path d="M5 3v4M19 17v4M3 5h4M17 19h4" />
    </svg>
  );
}
