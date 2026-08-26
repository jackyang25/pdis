import type { Tone } from "@/lib/tone";
import { TONE_TINT } from "@/lib/tone";
import { cn } from "@/lib/utils";

/**
 * One judgement about one thing, as a filled pill.
 *
 * The result surfaces carry three kinds of pill and each answers a different question,
 * so each has one owner and none borrows another's shape:
 *
 *   verdict   how this thing stands, judged. Tinted by tone, `rounded-md` - this.
 *   category  what kind of thing it is, observed. Outlined, `rounded-full` - `Badge`.
 *   count     how many of each verdict there are. A dot and a number, deliberately not
 *             a pill at all, because several sit in a row and the reader is comparing
 *             figures rather than hunting one verdict - `SignalChip`.
 *
 * A verdict is tinted and a category is outlined because a judgement is the thing a
 * reader is looking for and a category is how they narrow to it. Tint carries weight;
 * an outline does not.
 *
 * This exists because the verdict shape had drifted into three. Inspector's section list
 * drew a tinted `rounded-md` pill, while the Scout and Inspector trace panels each
 * hand-wrote the same `rounded-full border-border/80 bg-foreground/[0.045]` - a *neutral*
 * pill, character for character identical across the two files, for a value that is
 * never neutral. Both panels had the tone available on the annotation and threw it away,
 * so the same verdict was tinted in a list and grey in the panel that explains it.
 */
export function VerdictPill({
  label,
  tone,
  description,
  className,
}: {
  /** The short form. A description belongs in `description`, not here: one panel used
   *  to render the sentence as pill text and it wrapped onto two lines. */
  label: string;
  tone: Tone;
  /** The full sentence, on hover. */
  description?: string;
  className?: string;
}) {
  return (
    <span
      title={description}
      className={cn(
        "inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium",
        TONE_TINT[tone],
        className,
      )}
    >
      {label}
    </span>
  );
}
