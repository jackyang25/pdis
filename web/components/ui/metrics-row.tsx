import { VerdictCounts, type VerdictCount } from "@/components/ui/verdict-counts";

/**
 * How a run came out: the denominator, the distribution over it, and anything outside it.
 *
 * Four tools answered one question in four shapes. Inspector drew dotted counts anchored
 * to nothing - "1 not present" reads very differently against twelve units and three
 * hundred. Aligner put a help icon on its denominator, three lines under a sentence that
 * already explained it. Screener used a `dl` of value-label pairs with neither dot nor
 * total, then repeated its total in a closing paragraph. Scout wrote prose.
 *
 * The order is the argument, and it is why this is a component rather than a rule written
 * down somewhere:
 *
 *   denominator   what was examined, so every figure after it has something to be a
 *                 fraction of
 *   distribution  one bucket per verdict, summing to that denominator. A reader can
 *                 check the arithmetic, which is the whole reason to state a total.
 *   aside         facts that are true of the run but are not part of that sum -
 *                 Inspector's cross-section conflicts, Screener's required-and-open
 *                 count. Separated because a figure standing in the row would break the
 *                 sum a reader has just been invited to check.
 *
 * What stays with each tool is which entries appear and what they are called: the outcome
 * vocabulary is the one thing about a tool that cannot be shared. How the row reads is
 * not, and it was the only part that differed.
 *
 * No help affordance here, by rule. `ResultLayout` requires a `metricsNote`, which opens
 * the panel with a sentence saying what these figures count; a tooltip inside answers a
 * question the reader has had answered three lines above. Where a tool needs to explain a
 * word, it belongs in that note.
 */
export function MetricsRow({
  total,
  unit,
  items,
  facts = [],
}: {
  /** How many things were examined. The denominator every count below is part of. */
  total: number;
  /**
   * What was counted, singular and plural: `["unit", "units"]`.
   *
   * A pair rather than a formatted string, so no tool renders "1 units" and none of them
   * has to remember to check.
   */
  unit: readonly [string, string];
  /**
   * One entry per verdict, summing to `total`.
   *
   * Whether a zero appears is the tool's call and a real one: Screener shows a zero
   * `answered` because a model decided it and the zero says the check ran, while Inspector
   * hides a zero shortfall because a thing that did not happen is not a fact about the
   * document.
   */
  items: readonly VerdictCount[];
  /**
   * Figures about the run that are not part of the distribution.
   *
   * A list rather than free markup, and that is the whole point. This was a `ReactNode`,
   * so the three tools that use it wrote three different things into it: Inspector a
   * figure, Scout four figures joined by prose, Screener two full sentences with a rule
   * above one of them. One panel per tool, three ideas of what a panel is.
   *
   * A fact is a figure and what it counts. Anything that is not - a caveat, a definition,
   * an explanation of how the counts relate - is prose about the figures and belongs in
   * `metricsNote`, which is the one place this panel says anything in sentences.
   */
  facts?: readonly { value: string | number; label: string }[];
}) {
  return (
    <div className="space-y-2">
      {/* One line. The total and the distribution are one statement - this many things,
          and here is how they came out - and Screener stacked them, which read as two. */}
      <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
        <p className="text-xs font-medium">
          {total.toLocaleString()} {total === 1 ? unit[0] : unit[1]}
        </p>
        <VerdictCounts items={items} />
      </div>
      {/* One line each, figure then what it counts - the same reading order as the
          denominator above, so the whole panel is figures in one direction. No dots:
          a dot marks a member of the distribution, and these are outside it. */}
      {facts.length > 0 && (
        <ul className="space-y-1">
          {facts.map((fact) => (
            <li key={fact.label} className="text-[11px] text-muted-foreground">
              <span className="font-medium tabular-nums text-foreground">
                {typeof fact.value === "number"
                  ? fact.value.toLocaleString()
                  : fact.value}
              </span>{" "}
              {fact.label}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
