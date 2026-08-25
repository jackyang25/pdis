/**
 * The recurring text shapes, named once.
 *
 * Same idea as `lib/motion.ts` and `lib/tone.ts`: a recipe per kind of thing, imported
 * rather than remembered. A class string rather than a component, because the element these
 * sit on is a semantic choice the call site has to keep making. An eyebrow above a value in
 * a definition list is a `<dt>`; the same eyebrow over a panel is a `<p>`; over a table
 * column it is a `<span>` inside a header row. Wrapping that in a polymorphic component
 * would hide a decision that should stay visible.
 *
 * The audit that produced this file: the eyebrow appeared 22 times in one form and 14 more
 * in near-variants, across five letter-spacings (`tracking-wide`, `[0.08em]`, `[0.1em]`,
 * `[0.12em]`, `[0.14em]`) and two weights. Nothing distinguished them. They are the same
 * label doing the same job, and the differences were the residue of whoever typed each one.
 */

/**
 * The small capitalised label above a value, a panel, or a column.
 *
 * `tracking-wide` and `font-medium`, which is the form 22 of the 36 already used. Layout and
 * colour belong at the call site: a responsive `sm:hidden` on a mobile-only column header is
 * a different concern from what an eyebrow is.
 */
export const EYEBROW =
  "text-[10px] font-medium uppercase tracking-wide text-muted-foreground";

/**
 * A count beside a label, or a measured value in a column.
 *
 * `tabular-nums` is the whole point: a column of counts that do not line up is harder to
 * scan than no column at all. Ten files wrote this out, and one of them at a size larger
 * than the rest.
 */
export const COUNT = "text-[11px] tabular-nums text-muted-foreground";
