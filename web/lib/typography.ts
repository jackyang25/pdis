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
 * A heading that titles something.
 *
 * The Gates Foundation's serif, which is where their own `--font-display` token puts the
 * display face. Applied here rather than to `h1, h2, h3` in the stylesheet, because a tag does
 * not say what a heading is doing: an `h3` is a 17px tool card title in one place and a 14px
 * field label in a dense list in another, and `h2` is used for a 10px uppercase eyebrow in two.
 *
 * The rule is what the heading does, not how large it is:
 *
 *   titles something   a page, a panel, a card, a section of a page   -> the serif
 *   labels something   a row, a group inside a result, a form field   -> the sans
 *
 * The size break falls out of that at about 15px, which is the point below which a heading in
 * this interface is labelling rather than titling.
 *
 * The tag rule got this wrong in both directions. It put the serif on twelve `sm` and `xs`
 * headings that label rows inside a result, and on two eyebrows: a 10px uppercase label set in
 * a serif. It was invisible while the display face was Inter Tight, a sans, and became a
 * hundred unexamined decisions the moment the face changed.
 */
export const DISPLAY_HEADING = "font-display tracking-[0.005em]";

/**
 * A count beside a label, or a measured value in a column.
 *
 * `tabular-nums` is the whole point: a column of counts that do not line up is harder to
 * scan than no column at all. Ten files wrote this out, and one of them at a size larger
 * than the rest.
 */
export const COUNT = "text-[11px] tabular-nums text-muted-foreground";

/**
 * Nothing in this interface tightens its letter-spacing.
 *
 * Not a recipe, a rule, so there is no constant to import: the correct value is the font's
 * own, and any class here is an override of it.
 *
 * There were fifteen overrides across seven values - `-0.01em` through `-0.04em`, plus
 * `tracking-tight` - and they were not arbitrary. They were a size-indexed ramp: 36px took
 * `-0.04em`, 28px took `-0.035em`, 20px took `-0.03em`, 12px took `-0.01em`. That is the right
 * instinct for Inter, a grotesque whose default spacing is generous at display sizes.
 *
 * Both faces are now the Gates Foundation's. Noto Serif carries the headings and is spaced for
 * reading already, so negative tracking closes the gaps its own serifs exist to hold open.
 * Noto Sans carries the rest, at 10 and 11px for most of a result, where it is drawn to be
 * legible and tightening costs exactly that. Twelve of the fifteen overrides were on an `h1`,
 * `h2` or `h3`, fighting the rule `globals.css` already sets for the display face.
 *
 * `brand.test.ts` fails on a negative tracking class anywhere in `app/` or `components/`.
 */
