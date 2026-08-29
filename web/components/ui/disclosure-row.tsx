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
   * Whether the group starts open.
   *
   * A judgement about the data, so it stays with the caller. Scout's groups start closed
   * because a field carries several and most hold nothing a reader has to act on; Aligner
   * opens its verdict groups because the tab exists to show them and a column of five
   * closed rows is a second navigation step to the thing already navigated to.
   */
  defaultOpen?: boolean;
  children: ReactNode;
}) {
  return (
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
