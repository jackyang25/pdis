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
 * Not to be confused with the plot key in `comparator-distribution-plot.tsx`, which is
 * larger and filled-or-hollow: that marks which points are which in a chart, not what a
 * result came out as, and it should keep looking different.
 */
export function ToneDot({ tone, className }: { tone: Tone; className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cn("h-1.5 w-1.5 shrink-0 rounded-full", TONE_DOT[tone], className)}
    />
  );
}
