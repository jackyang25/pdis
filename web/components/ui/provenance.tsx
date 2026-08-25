"use client";

import type { LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";

/**
 * The affordance for "where did this come from".
 *
 * One button shape for every direction of provenance, so a reader learns it once and then
 * recognises it everywhere. Scout has four of them and they were four copies of the same
 * two hundred characters of class names, which is how a fifth would have drifted:
 *
 *     In document    a passage of the uploaded file
 *     Sources        the findings behind an insight, and the searches that returned them
 *     Comparators    the measurements a target's statistics were computed from
 *     Excluded       what a comparison left out, and why
 *
 * Each names what it holds and carries its own count. The label is always a noun, never an
 * instruction: "View source" was an instruction that named neither direction, and a reader
 * could not tell it from the citations beside it.
 *
 * Every panel behind one of these uses `TracePanelHeader`, so the eyebrow, title and
 * one-line description are in the same place in all four.
 */
export function ProvenanceTrigger({
  icon: Icon,
  label,
  count,
  ariaLabel,
}: {
  icon: LucideIcon;
  /** A noun for what the panel holds. */
  label: string;
  /** Always rendered when given. Suppressing it at one made two triggers look like two
   *  different kinds of control. */
  count?: number;
  ariaLabel: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex h-7 shrink-0 items-center gap-1.5 whitespace-nowrap rounded-md border border-transparent px-2",
        // The pair stays on one line: `motion-standard.test.ts` reads them together, and a
        // transition whose reduced-motion companion is a line away is one nobody can audit.
        "text-[10px] font-medium text-muted-foreground transition-colors motion-reduce:transition-none",
        "hover:border-border hover:bg-muted/60 hover:text-foreground",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/20",
      )}
      aria-label={ariaLabel}
    >
      <Icon className="h-3 w-3" aria-hidden="true" />
      {label}
      {count != null && (
        /* Two digits wide, right-aligned, so the count cannot move the label.

           These are read down a column, and the label is what a reader scans - but the
           count is the last element in a right-packed row, so one extra digit shifted
           everything left of it: `Excluded 32` sat a digit further left than `Excluded 7`
           directly above it. Reserving the width here rather than at the row keeps the
           trigger one shape wherever it is used. `tabular-nums` makes the reservation
           exact; without it the glyphs themselves vary. Three digits still widen it, which
           is the right trade for a count that rare. */
        <span className="min-w-[2ch] text-right tabular-nums">{count}</span>
      )}
    </span>
  );
}

/**
 * Stops a trigger inside a clickable row from opening that row.
 *
 * Every one of these sits on a `<summary>` or a list item that toggles, so the handlers are
 * the same in all four and belong here rather than being remembered per call site.
 */
/**
 * The geometry every provenance panel opens at.
 *
 * Four panels wrote `w-[min(720px,calc(100vw-24px))]` and three wrote
 * `max-h-[min(60vh,520px)]`, beside near-variants at 58vh and 76vh and at 300, 320 and
 * 360px. A reader opens these one after another on one row, so a panel that is 20px narrower
 * than the last reads as a different kind of thing.
 *
 * The width is the reading measure minus a gutter; the height stops a long cohort from
 * covering the row it belongs to. Both are here rather than in a Tailwind theme key because
 * they are one pair of values for one component, not a scale.
 *
 * Deliberately not applied to two other popovers: the distribution plot's 300px card
 * describes a single point under the cursor, and `signal-help` opens a paragraph, not a list.
 * Both are tooltips rather than panels, and giving a tooltip a panel's measure would say it
 * holds something it does not.
 */
export const PROVENANCE_PANEL = {
  width: "w-[min(720px,calc(100vw-24px))]",
  scroll: "max-h-[min(60vh,520px)]",
} as const;

export const stopRowToggle = {
  onClick: (event: React.MouseEvent) => event.stopPropagation(),
  onPointerDown: (event: React.PointerEvent) => event.stopPropagation(),
  onKeyDown: (event: React.KeyboardEvent) => event.stopPropagation(),
} as const;
