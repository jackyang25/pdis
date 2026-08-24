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
      {count != null && <span className="tabular-nums">{count}</span>}
    </span>
  );
}

/**
 * Reserved widths for a row that can show several triggers.
 *
 * A slot holds its width even when its trigger is absent, which is what keeps every trigger
 * in one column down a list where some rows have three and some have one. Declared here
 * rather than written at each call site: three magic numbers in three files drift the moment
 * a label gets a word longer.
 *
 * Sized to the longest label each slot can hold, plus its count. A row with a single trigger
 * needs none of this and should not reserve the others: an empty 14rem of nothing to align a
 * button against a different table is space taken from the document's own text.
 */
export const PROVENANCE_SLOT = {
  /** "Comparators 12" */
  comparators: "w-[7.5rem]",
  /** "Excluded 12" */
  excluded: "w-[6.5rem]",
} as const;

/* No entry for `In document`. A row showing only that trigger states its width as a grid
 * column, and Tailwind resolves arbitrary values at build time, so it cannot come from a
 * constant. It also appears once, which is the case a constant does not help. */

/**
 * Stops a trigger inside a clickable row from opening that row.
 *
 * Every one of these sits on a `<summary>` or a list item that toggles, so the handlers are
 * the same in all four and belong here rather than being remembered per call site.
 */
export const stopRowToggle = {
  onClick: (event: React.MouseEvent) => event.stopPropagation(),
  onPointerDown: (event: React.PointerEvent) => event.stopPropagation(),
  onKeyDown: (event: React.KeyboardEvent) => event.stopPropagation(),
} as const;
