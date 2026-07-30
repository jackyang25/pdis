/**
 * The app's motion standard: one recipe per kind of state change.
 *
 * One recipe per kind of state change, rather than a choice per component. Importing a recipe is how a
 * surface stays consistent with its peers; inventing a duration or omitting a
 * reduced-motion companion fails `motion-standard.test.ts`.
 *
 * Durations and easings come from `tailwind.config.ts` (fast 120ms, base 180ms,
 * slow 320ms). Nothing here should hold a raw millisecond value.
 */

/** Body revealed by a `details` element or popover. */
export const DISCLOSURE_MOTION =
  "animate-in fade-in duration-base ease-enter motion-reduce:animate-none";

/** Content that has finished loading and is taking its place on the page. */
export const CONTENT_ARRIVAL_MOTION =
  "animate-fade-rise motion-reduce:animate-none";

/**
 * A surface entering at full width — a review checkpoint or a result panel.
 * The only place `duration-slow` is appropriate.
 */
export const SURFACE_ENTRY_MOTION =
  "animate-in fade-in duration-slow ease-enter motion-reduce:animate-none";

/**
 * The caret on a message still being streamed. Like a spinner, its movement is
 * the status, so it keeps moving under reduced motion — there is no other cue
 * that generation is ongoing.
 */
export const STREAM_CARET_MOTION = "animate-pulse";
