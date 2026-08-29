import { SignalChip } from "@/components/ui/signal-chip";
import type { Tone } from "@/lib/tone";
import { cn } from "@/lib/utils";

/**
 * How many of each verdict, in one row.
 *
 * Every tool needed this and every tool built it: Scout as dot chips, Inspector as tinted
 * pills, Aligner as plain muted text, Screener as labelled cells. Four presentations of one
 * idea, which a reader moving between tools has to learn four times, and none of them
 * wrong on its own - that is what made it survive.
 *
 * What each caller keeps is the part that is genuinely theirs: **which entries appear**.
 * Screener shows `answered` and `not found` even at zero, because those two are decided by a
 * model and a zero there says the check ran and found nothing; Inspector hides a zero,
 * because a shortfall that did not occur is not a fact about the document. That is a
 * judgement about the data and belongs to the tool. How the row looks is not.
 *
 * Dots rather than tints, per the rule in `lib/tone.ts`: several signals share this row and
 * none is dominant, so the reader is comparing counts rather than hunting one verdict.
 */
export type VerdictCount = {
  /** The verdict, in the tool's own vocabulary. */
  label: string;
  count: number;
  tone: Tone;
};

export function VerdictCounts({
  items,
  className,
}: {
  items: readonly VerdictCount[];
  className?: string;
}) {
  if (items.length === 0) return null;
  return (
    <div className={cn("flex flex-wrap items-center gap-x-4 gap-y-1.5", className)}>
      {items.map(({ label, count, tone }) => (
        <SignalChip key={label} tone={tone}>
          {label}
          {/* Tabular, so a column of these lines up down a list of sections. */}
          <span className="tabular-nums text-muted-foreground">{count}</span>
        </SignalChip>
      ))}
    </div>
  );
}
