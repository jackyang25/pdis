/**
 * Whether the product header is showing, as a function of where the page is.
 *
 * A pure decision rather than logic inside a scroll handler, for the reason every other
 * derivation in this folder is pure: the interesting part is the rules, and the rules are what
 * a test can hold. The hook that drives it only reads `window.scrollY` and calls this.
 *
 * The header is 56px and sits above a breadcrumb. On a Scout result that runs thousands of
 * pixels, it is a band of chrome permanently covering the thing being read. So it leaves on
 * the way down and comes back on the way up, which is where a reader wants it: reaching for
 * navigation is an upward gesture.
 */

/**
 * How far down the page the header may first hide.
 *
 * Its own height plus a little. Below this the header has not yet been scrolled past, so
 * hiding it would remove something the reader can still see rather than something in the way.
 */
export const HEADER_HIDE_AFTER = 64;

/**
 * The smallest scroll that counts as a direction.
 *
 * A trackpad emits a continuous drizzle of one and two pixel events, often alternating sign at
 * the end of a fling. Without a floor the header flickers, which is worse than a header that
 * never moves.
 */
export const HEADER_SCROLL_DELTA = 6;

export type HeaderVisibility = "visible" | "hidden";

export function nextHeaderVisibility(
  current: HeaderVisibility,
  {
    scrollY,
    previousScrollY,
    reduceMotion,
  }: { scrollY: number; previousScrollY: number; reduceMotion: boolean },
): HeaderVisibility {
  // A reader who asked for less motion gets a header that does not move. Not a header that
  // appears and disappears without a transition, which is the same movement with the easing
  // removed: more startling, not less.
  if (reduceMotion) return "visible";

  // Includes the negative values an elastic overscroll produces at the top of a page.
  if (scrollY <= HEADER_HIDE_AFTER) return "visible";

  const delta = scrollY - previousScrollY;
  if (Math.abs(delta) < HEADER_SCROLL_DELTA) return current;
  return delta > 0 ? "hidden" : "visible";
}
