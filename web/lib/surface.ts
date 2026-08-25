/**
 * The tinted surfaces, named by the job each one does.
 *
 * Same idea as `lib/tone.ts` and `lib/typography.ts`. There were **twelve** values of one
 * tint across the app, `bg-muted` and eleven opacities from /10 to /70, with nothing
 * declaring what any rung meant. A header band was /10 in one place, /15 in another, /30 in
 * a third and /35 in a fourth. Hovering a row was one of seven values depending on the file.
 * A selected row was /45, /50 or /70.
 *
 * **The tint is the foreground, not `--muted`.** That is why twelve rungs existed. `--muted`
 * is `96%` lightness, four points from white, so every opacity of it is squeezed into those
 * four points: /15 lands 0.6 of a point off white and /30 lands 1.2. They were all nearly
 * invisible, so each author bumped the number trying to see the thing they had just drawn,
 * and the ladder grew a rung at a time. The first version of this file made the same
 * mistake: an open row's body at `bg-muted/[0.08]` is 0.32 of a point off white, which is
 * nothing at all.
 *
 * The foreground is `12%` in light mode and `95%` in dark, so a low alpha of it gives a real
 * grey, and the same alpha gives the same visible step in both modes: /0.045 is 4.4 points
 * off a white card and 4.2 points off a dark one. Three steps and a solid cover every job.
 *
 * Sampling every use turned up five jobs and no more:
 *
 *   RECESSED  set back from the content around it: a toolbar, a footer, a table header,
 *             a nested block. Its border is what says which of those it is; the tint only
 *             says "not the main surface".
 *   OPEN      the extent of a row that is currently expanded.
 *   HOVER     a row answering the cursor.
 *   SELECTED  the row a reader has chosen, which stays chosen after the cursor leaves.
 *   FILL      a solid shape: a progress track, a placeholder block.
 *
 * `OPEN` is two values, and that is the point of it. The summary takes the darker one as the
 * row's header and the body takes the lighter, so an open row reads as a single block from
 * its first line to its last. Before this only the summary was tinted, so the start of an
 * open row was marked and the end was not: scrolling into a long body left no signal that
 * you were still inside one.
 */

export const SURFACE = {
  /** A strip or block set back from the content around it. */
  recessed: "bg-foreground/[0.045]",

  open: {
    /**
     * On the summary line.
     *
     * Written with its state prefix rather than composed at the call site: Tailwind reads
     * class names literally out of the source, so a template string builds a class that
     * never reaches the stylesheet.
     */
    header: "group-open/expand:bg-foreground/[0.07]",
    /** The lightest step. It runs the height of a body, so it only has to be perceptible. */
    body: "bg-foreground/[0.025]",
  },

  /**
   * A row answering the cursor.
   *
   * The same step as `recessed`, deliberately: a band and a hovered row are the same weight,
   * and what tells them apart is that one of them moves.
   */
  hover: "hover:bg-foreground/[0.045]",

  /** The row a reader chose. Heavier than hover, because it outlasts the cursor. */
  selected: "bg-foreground/[0.07]",

  /**
   * A solid shape rather than a wash: a progress track, a placeholder.
   *
   * `--muted` itself, not an alpha of the foreground. This is a filled object with an edge,
   * not a tint over whatever is behind it.
   */
  fill: "bg-muted",
} as const;
