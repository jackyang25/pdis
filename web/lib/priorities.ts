/**
 * What the four priority selectors and the panel that renders them agree on.
 *
 * Here rather than in `components/ui/priority-panel.tsx`, where the shape used to live.
 * Six modules under `lib/` reached up into a component for it, which is backwards - the
 * item is data a selector produces and a panel happens to draw - and it only ever worked
 * because the import was type-only and erased before anything had to resolve it. The
 * limit below is a value, so the first thing it did was break the test runner.
 */

/** One thing to look at first, in the tool's own words. */
export type PriorityItem = {
  id: string;
  /** What it is about: a field, a rubric unit, a requirement. */
  label: string;
  /** The kind of problem, so a column of these can be scanned for one of them. */
  qualifier?: string;
  statement: string;
  recommendation?: string;
  /** Passages behind it, for the source trigger. */
  blockIds?: string[];
};

/**
 * How many priorities a panel shows.
 *
 * A starting point, not the whole result. Scout capped at eight and stated why; the other
 * three returned everything their rule raised, which for Inspector is the entire worklist -
 * eighteen findings on a normal run, each four lines with a source trigger, so opening the
 * panel pushed every result off the screen it was supposed to introduce.
 *
 * A default rather than a limit: the panel shows this many and offers the rest on a
 * button. The distinction matters because these are a worklist, not a ranked sample -
 * every one of Inspector's is a rubric unit somebody has to go and fix - so ten unshown
 * items are ten jobs, and pointing at the tab below asks a reader to find rows they
 * cannot identify. Scout's own order note calls its ranking "a placeholder until a rubric
 * defines what matters most", which makes a hard cut through it a cut at an arbitrary
 * point in an arbitrary order.
 *
 * Not a scrolling box either. The panel opens closed, so a scrollbar inside something you
 * just opened hides what you asked for, and a nested scroll region captures the wheel on
 * the way past.
 *
 * Eight because that is what Scout settled on, and no argument has been made for a
 * different number in the other three.
 */
export const PRIORITY_LIMIT = 8;
