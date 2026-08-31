"use client";

import { ChevronDown } from "lucide-react";
import type { ReactNode } from "react";

import { ToneDot } from "@/components/ui/tone-dot";
import { DISCLOSURE_MOTION } from "@/lib/motion";
import type { Tone } from "@/lib/tone";
import { cn } from "@/lib/utils";

/**
 * A group of results under one heading a reader can close.
 *
 * The heading is the shape every tool uses for a group - a dot for the verdict, the word,
 * and how many are in it - and the row it heads collapses, which is the part Aligner did
 * not have. Aligner listed five verdict groups open, one after another, so a reader who
 * came for the six shortfalls scrolled past the forty-seven requirements that were fine to
 * reach the next group.
 *
 * Lived in `app/scout/page.tsx` as a private component while Aligner rendered a bare chip
 * over an open list. Same mark, half the affordance, and nothing recorded that as a
 * decision.
 *
 * Not `CollapsibleCard`, which draws a bordered box and is the level above this: a card
 * holds a section, a discipline, or a comparison, and these are the groups inside one.
 * Nesting a box in a box was the thing Inspector's section list had to stop doing.
 */
export function DisclosureRow({
  label,
  tone,
  count,
  note,
  defaultOpen = false,
  children,
}: {
  label: string;
  /** The verdict this row groups, when it groups one. */
  tone?: Tone;
  count: number;
  /** Shown only when something is off, e.g. a citation naming an insight not retained. */
  note?: string;
  /**
   * Whether the group starts open. Closed unless a caller has a reason.
   *
   * The one reason so far is a search: on arrival a closed group states its verdict and
   * its count, which is the answer for most readers, but once someone has typed, every
   * row still here is one they asked for and two more clicks to reach it is a filing
   * cabinet in place of a result.
   */
  defaultOpen?: boolean;
  children: ReactNode;
}) {
  return (
    // Closed on arrival, like every other group in the suite. A heading states its
    // verdict and its count, so the closed row already answers most of what a reader came
    // for; opening one is for the single group they want the requirements behind.
    <details className="group/row" open={defaultOpen}>
      <summary className="flex cursor-pointer select-none items-center gap-2 py-1.5 outline-none focus-visible:ring-2 focus-visible:ring-ring/20 [&::-webkit-details-marker]:hidden">
        <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground transition-transform group-open/row:rotate-180 motion-reduce:transition-none" />
        {tone && <ToneDot tone={tone} />}
        <span className="text-xs font-medium text-foreground">{label}</span>
        <span className="text-[11px] tabular-nums text-muted-foreground">{count}</span>
        {note && <span className="text-[11px] text-muted-foreground">{note}</span>}
      </summary>
      <div className={cn("pb-2 pl-5", DISCLOSURE_MOTION)}>{children}</div>
    </details>
  );
}
