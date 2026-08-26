"use client";

import { useState } from "react";
import { ChevronUp } from "lucide-react";

import { DocumentSourceTrace } from "@/components/document-source-trace";
import { Skeleton } from "@/components/ui/skeleton";
import type { PriorityNomination } from "@/lib/api";
import { PRIORITY_LIMIT, type PriorityItem } from "@/lib/priorities";
import { cn } from "@/lib/utils";

// Re-exported for the pages that import the panel and its item together.
export type { PriorityItem } from "@/lib/priorities";

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
 *
 * Three layers, and each answers a different question. They are kept visibly apart
 * because the moment they blur, the panel stops being checkable:
 *
 *   the list          what qualifies, and in what order — the tool's own rule, no model
 *   `digest`          what the list amounts to — describes only what is already listed
 *   `nominations`     what the rule left out — new items, each citing a passage
 *
 * A digest may not introduce an item and may not re-rank; a nomination may not repeat a
 * listed one. The first is a prompt rule, the second is enforced in the service, so a
 * model restating the list cannot produce a second copy of it here.
 */

/**
 * One thing worth looking at, in the shape every tool maps into.
 *
 * Deliberately small. A field here has to make sense for a rubric gap, a
 * contradicted target, and whatever the next tool produces - anything narrower
 * belongs in the tool's own view, not in the panel every tool shares.
 */

export function PriorityPanel({
  attribution,
  items,
  emptyMessage,
  orderNote,
  digest,
  nominations = [],
  digestLoading = false,
  digestError,
  title = "Priorities",
  /**
   * Closed, like every other disclosure on the page.
   *
   * It opened by default and nothing else did, so on a result whose sections, fields and
   * units all start closed this was the one thing already expanded - and the reader who
   * had read it once had to close it on every run. The count in its header states how many
   * there are without opening it, which is what a lede has to do.
   */
  defaultOpen = false,
}: {
  /**
   * Who produced the wording, always as `by <Tool>`.
   *
   * One grammar, because the panel reads `<count> <attribution>` and three tools
   * saying three different things there is three panels. Inspector used to pass
   * "in priority order", which answered a different question — the one `orderNote`
   * below already answers — and left the tool whose wording is model-written as the
   * only one not naming itself.
   */
  attribution: string;
  items: PriorityItem[];
  /** Shown instead of the list when there is nothing to raise. */
  emptyMessage: string;
  /** How the order was decided. Stated because the sparkle does not cover it. */
  orderNote: string;
  /**
   * A short passage about the list, when one has been read.
   *
   * Optional in every sense: the panel is complete without it, so a tool that does not
   * ask for one, or a read that failed, changes nothing else on the page.
   */
  digest?: string;
  /** Items the tool's rule excluded that were nominated for a second look. */
  nominations?: PriorityNomination[];
  /** A read is in flight. Space is held so the list below does not jump when it lands. */
  digestLoading?: boolean;
  /**
   * Why no digest arrived, when a read was attempted and failed.
   *
   * Said quietly rather than swallowed. A skeleton followed by nothing is
   * indistinguishable from a tool that never had a summary, and that ambiguity cost a
   * reader more than the missing paragraph did.
   */
  digestError?: string;
  /**
   * Overridden only by a tool whose own published vocabulary names this list
   * better than "Priorities" does. No tool currently does: Inspector's "Findings"
   * and Expert's "Gaps" were both removed, because a reader who learns this panel
   * in one tool should recognise it in the next, and the tool's own noun is already
   * on every row beneath it.
   */
  title?: string;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  // Two disclosures, not one, because they answer different questions: whether to look at
  // priorities at all, and whether eight is enough of them.
  const [showAll, setShowAll] = useState(false);
  const shown = showAll ? items : items.slice(0, PRIORITY_LIMIT);
  const hidden = items.length - shown.length;
  return (
    // No border and no corners: this is a band in the result layout, between the tab
    // row and the toolbar, and both of those are flush. A card here made the middle
    // one of three consecutive zones look like a component sitting inside the others.
    <section>
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
          {/* Above the list, because it is about the list. Below the list it would read
              as a conclusion drawn from it, which is a different claim. */}
          {digestLoading && !digest && (
            <div className="mb-4 space-y-1.5">
              <Skeleton className="h-3.5 w-full" />
              <Skeleton className="h-3.5 w-[88%]" />
            </div>
          )}
          {digest && (
            <p className="mb-4 whitespace-pre-line text-sm leading-6 text-foreground/85">
              {digest}
            </p>
          )}
          {!digest && !digestLoading && digestError && (
            <p className="mb-4 text-xs leading-5 text-muted-foreground">
              No summary for this run. {digestError}
            </p>
          )}
          {items.length > 0 ? (
            <ul className="space-y-3">
              {shown.map((item) => (
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
          {/* A button, not a sentence pointing at the tab below. These are a worklist -
              every one of Inspector's is a rubric unit somebody has to go and fix - so
              the ten it does not show are ten jobs, and "they are in the list below" asks
              a reader to go and find rows they cannot identify. The default stays eight,
              which is what keeps an eighteen-item panel from pushing the result off the
              screen it introduces; how many is enough is the reader's call, not ours. */}
          {items.length > PRIORITY_LIMIT && (
            <button
              type="button"
              onClick={() => setShowAll((current) => !current)}
              aria-expanded={showAll}
              className="mt-3 rounded-md text-xs font-medium text-muted-foreground underline-offset-4 transition-colors hover:text-foreground hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/20 motion-reduce:transition-none"
            >
              {showAll
                ? `Show the first ${PRIORITY_LIMIT}`
                : `Show all ${items.length}, ${hidden} more`}
            </button>
          )}
          {nominations.length > 0 && (
            /* Its own section, under its own heading. Inside the list it would become a
               priority the tool's rule never selected, and the panel could no longer say
               its order was decided by a stated rule. */
            <section className="mt-4 border-t border-border pt-3.5">
              <p className="flex items-center gap-1.5 text-xs font-medium text-foreground">
                <PriorityGlyph className="h-3.5 w-3.5" />
                Also worth looking at
                <span className="font-normal text-muted-foreground">
                  not selected by the rule above
                </span>
              </p>
              <ul className="mt-2 space-y-2.5">
                {nominations.map((nomination) => (
                  <li key={nomination.label} className="text-sm leading-6">
                    <p className="font-medium">{nomination.label}</p>
                    <p className="mt-0.5 text-muted-foreground">{nomination.statement}</p>
                    {nomination.cited_block_ids.length > 0 && (
                      <div className="mt-1.5">
                        <DocumentSourceTrace blockIds={nomination.cited_block_ids} />
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            </section>
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
function PriorityGlyph({ className }: { className?: string } = {}) {
  return (
    <svg
      aria-hidden
      viewBox="0 0 24 24"
      className={cn("h-4 w-4 shrink-0 fill-none stroke-current stroke-2", className)}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3Z" />
      <path d="M5 3v4M19 17v4M3 5h4M17 19h4" />
    </svg>
  );
}
