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
 * Where a jump landed.
 *
 * A reader sent from a result row, a coverage cell, or a passage in the panel needs
 * to see *which* block answered, and the scroll alone does not say so: the target
 * arrives mid-screen among identical-looking paragraphs. The ring holds for
 * `ARRIVAL_HIGHLIGHT_MS` and then releases, so it reads as an event rather than a
 * property of the block.
 *
 * A recipe rather than a class string in the viewer because three tools jump into the
 * same document trace and one of them will eventually grow its own way in. The ring
 * offset is on `card` because the reconstructed document sits on that surface.
 *
 * Pointedly **not** `--tone-marked`. That token means "a result cites this", and every
 * block a jump can land on is by definition cited — so an amber ring was drawn around
 * an already-amber block every single time, and the arrival read as a faint edge on the
 * mark rather than as an answer to "where did I just land". The foreground belongs to no
 * tone, which is what makes it legible over marked, cautioned, and danger-tinted blocks
 * alike: arrival is not a judgement about the passage, so it should not borrow a colour
 * that is one.
 *
 * Inset, and drawn on the block row itself, because that is literally what "a ring
 * around the block" is: it encloses the whole passage, gutter included, rather than
 * floating around its text column. It was an offset ring on the text, and an offset ring
 * paints outside the element's box, where a clipping ancestor can cut it away — which is
 * how it once showed as a single stray edge. Inset cannot be clipped by anything.
 *
 * The fade is owned by the block container, which already transitions its box-shadow.
 * Declaring a second `transition-property` here would leave which one applies up to
 * stylesheet order.
 */
export const ARRIVAL_HIGHLIGHT =
  "rounded-md ring-2 ring-inset ring-foreground/45";

/**
 * How long an arrival stays marked, in milliseconds.
 *
 * Held here beside the ring it governs: the duration is half of the signal, and a
 * component holding its own timeout is how one jump comes to flash longer than
 * another. Long enough to find with the eye after a smooth scroll settles, short
 * enough that it is plainly temporary.
 */
export const ARRIVAL_HIGHLIGHT_MS = 2200;

/**
 * The caret on a message still being streamed. Like a spinner, its movement is
 * the status, so it keeps moving under reduced motion — there is no other cue
 * that generation is ongoing.
 */
export const STREAM_CARET_MOTION = "animate-pulse";
