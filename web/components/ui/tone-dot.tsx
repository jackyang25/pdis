import { TONE_DOT, type Tone } from "@/lib/tone";
import { cn } from "@/lib/utils";

/**
 * The mark that carries a tone, at the size every surface draws it.
 *
 * One shape and one size, because the dot means the same thing everywhere it appears - a
 * verdict count, a grouped disclosure row, a node on the evidence map, an insight in a
 * cited list. Five surfaces hand-wrote `h-1.5 w-1.5 rounded-full` beside a `TONE_DOT`
 * lookup, and one of them wrote the colour values out instead of looking them up, which
 * is how the evidence map ended up with `neutral` a different colour from every other
 * neutral in the interface.
 *
 * **The shape says what kind of thing is marked, never which vocabulary it belongs to.**
 * That is the rule, and it is the answer to why one screen can show `answered` as a dot in
 * the figure row and as a square in the coverage strip below it. Three shapes exist and
 * each has one job:
 *
 *   dot        a verdict standing beside a label. The label carries the meaning and the
 *              dot carries the tone. Every figure row, every group heading, every
 *              disclosure.
 *   grid cell  the datum itself. A cell in the coverage strip *is* one question - it has
 *              area because a square of them is the run - so it is drawn as a square, and
 *              the legend under it uses squares because a legend shows the mark of the
 *              thing it explains. A dot there would key a grid of squares to a row of
 *              dots.
 *   plot key   a chart's own point style, filled or hollow, in
 *              `comparator-distribution-plot.tsx`. Same reason as the grid: it explains
 *              marks that already exist on a canvas.
 *
 * So a tone renders as a dot everywhere except inside something that draws its own marks,
 * where it renders as those. What must never differ is the *colour*: one tone scale,
 * `TONE_DOT`, whatever the shape.
 */
export function ToneDot({ tone, className }: { tone: Tone; className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cn("h-1.5 w-1.5 shrink-0 rounded-full", TONE_DOT[tone], className)}
    />
  );
}
