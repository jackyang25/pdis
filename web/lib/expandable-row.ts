import { SURFACE } from "@/lib/surface";
import { cn } from "@/lib/utils";

/**
 * The summary line of a full-width row that opens: an indicator, a program, a safety
 * observation, a field, a rubric unit.
 *
 * One string, because four of them existed in Scout and three agreed. The safety row had
 * drifted to a lighter hover, a stronger focus ring, a fainter open tint, no focus
 * background, and a minimum height the others did not have - each reading as a deliberate
 * distinction when nothing distinguishes the rows.
 *
 * The group scope is shared too, so a row cannot half-adopt this by keeping its own name.
 * It is `expand`, not `row`, because Scout's `DisclosureRow` owns `row` for the smaller
 * in-field groups and one of these rows contains those.
 *
 * Lived in Scout, which is the tool that has this right: a field is read beside 27 others,
 * so every row is one line until a reader opens it. Inspector rendered all 32 of its units
 * expanded at once - each carrying a reason, a statement, a recommendation and a
 * provenance trigger - so a section was a wall rather than a list, and adjacent rows
 * differed in height by a factor of nine.
 *
 * The tint pairs with `SURFACE.open.body` on the content beneath: the summary is the open
 * row's header, and only tinting this line marked where a row began and never where it
 * ended.
 */
export const EXPANDABLE_ROW = cn(
  "flex cursor-pointer select-none items-start gap-4 px-5 py-4 outline-none transition-colors focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring/20 sm:px-6 [&::-webkit-details-marker]:hidden motion-reduce:transition-none",
  SURFACE.hover,
  "focus-visible:bg-foreground/[0.045]",
  SURFACE.open.header,
);
