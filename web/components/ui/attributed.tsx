import type { ReactNode } from "react";

import { Reading } from "@/components/ui/evidence-text";
import { cn } from "@/lib/utils";

/**
 * One model sentence, and the short label saying what it is.
 *
 * Two sentences from a model look identical, because the authorship mark is the same on
 * both and so is the tone. Where a row holds more than one, only a label separates them -
 * Aligner's row carries the bar from one document beside the answer from the other, and
 * Screener's carries what the material says beside what it still does not.
 *
 * The label **leads the line** rather than sitting above it. Aligner's used to be a
 * trigger at the bottom of the row reading "In document" on both sentences, so a reader
 * met two near-identical lines and learned which was which only after reading both.
 * Screener's sat inside the sentence, which put the tool's word inside a model's
 * quotation.
 *
 * Lived in `app/aligner/page.tsx`. Promoted when Screener turned out to need the same
 * thing: one label, one sentence, one baseline.
 */
export function Attributed({
  label,
  size = "prominent",
  continued = false,
  children,
  trailing,
  className,
}: {
  /** What this sentence is: a document's name, or what it leaves open. */
  label: string;
  /** `prominent` where the sentence is the row's subject, `body` where it follows one. */
  size?: "body" | "prominent";
  /**
   * Whether this continues the sentence above it rather than standing beside it.
   *
   * Aligner's two lines are two contributions - a requirement read from one document, an
   * answer read from another - so both carry the authorship mark. Screener's are one: the
   * model's answer, then what that answer still leaves open. Two marks stacked read as a
   * list of equals, so the second goes unmarked and the label carries the distinction
   * instead.
   *
   * The leading indent `Reading` adds for a continuation is dropped here, because the
   * label already occupies that space: applied inside the row it would push the sentence
   * clear of the label rather than aligning it under the line above.
   */
  continued?: boolean;
  children: ReactNode;
  /** The passages it was read from, or anything else that ends the line. */
  trailing?: ReactNode;
  /** Spacing only. The line's own layout belongs to this component. */
  className?: string;
}) {
  return (
    <div className={cn("flex flex-wrap items-baseline gap-x-2", className)}>
      <span className="shrink-0 text-[11px] font-medium text-muted-foreground">
        {label}
      </span>
      <Reading
        size={size}
        continued={continued}
        className={cn("mt-0 min-w-0 flex-1", continued && "pl-0")}
      >
        {children}
      </Reading>
      {trailing}
    </div>
  );
}
