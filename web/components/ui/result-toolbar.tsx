import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/**
 * The controls for one tab's content, directly under the tab row.
 *
 * There are four zones on a result and, until this existed, no rule about which held what:
 *
 *   header    who this result is about, and what you can do with the whole run
 *   tab row   navigation, and nothing else
 *   toolbar   what filters, searches, counts or explains the content below it
 *   content   the result itself, including any summary derived from it
 *
 * Every tool had a toolbar and every tool placed it differently. Scout wrote this same band
 * twice and put "How to read" inside it on one tab; Inspector put "How to read" on the tab
 * row, where it applies to navigation rather than to anything; Scout's Fields tab had the
 * toolbar *below* a stats line and a priorities panel, so the chrome sat inside the content
 * it controls.
 *
 * A summary is content, not chrome. It is derived from what is below it and moves with it,
 * which is why the rule puts it under this rather than above.
 */
export function ResultToolbar({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col gap-2 border-b border-border/60 bg-foreground/[0.045] px-5 py-3 sm:flex-row sm:items-center sm:px-6",
        className,
      )}
    >
      {children}
    </div>
  );
}

/**
 * The right-hand end of a toolbar: how much of the content you are looking at, and what
 * explains it.
 *
 * Named because all three tools ended their toolbar the same way and each wrote the
 * alignment out by hand. Two things it now decides for them, because both were got
 * wrong in the same place and neither is a per-tool judgement:
 *
 * **Order.** The explainer is last. It is the one item here whose width never changes,
 * so putting it outermost gives the row a fixed right edge; with the count outside it,
 * filtering from `36 of 36` to `4 of 36` shifted every control on the band.
 *
 * **Silence.** A count equal to the total is not a fact about the result - `36 of 36`
 * is the filter telling you it is not filtering, next to a subtitle that already said
 * 36. It renders only once the two differ.
 */
export function ResultToolbarEnd({
  count,
  children,
}: {
  /**
   * How many rows survive the controls to the left, out of how many there are.
   *
   * Omitted where there is nothing to filter. Passed as the pair rather than as text so
   * the decision to stay quiet is made once here, not remembered at five call sites.
   */
  count?: { shown: number; total: number };
  /** What explains the content. Rendered last, at the fixed right edge. */
  children: ReactNode;
}) {
  return (
    <div className="flex w-full items-center justify-between gap-3 sm:ml-auto sm:w-auto sm:justify-start">
      {count && count.shown !== count.total && (
        <span
          role="status"
          aria-live="polite"
          className="text-[11px] tabular-nums text-muted-foreground"
        >
          {count.shown} of {count.total}
        </span>
      )}
      {children}
    </div>
  );
}
