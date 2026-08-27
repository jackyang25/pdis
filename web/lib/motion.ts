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
 * A card answering the cursor: it is a target, and hovering says so.
 *
 * A recipe rather than a class string on each card, for the reason the others are: two
 * card kinds use it, and "how a card responds" should not be two answers. It was a border
 * one shade darker plus a 5%-opacity shadow, which on a near-white background is
 * invisible — the cards looked flat because they did not visibly respond, not because they
 * lacked ornament.
 *
 * A lift and a shadow, and nothing that runs on its own. A perpetually animating border —
 * the fashionable version of this — is decoration rather than a state change, so it has no
 * honest reduced-motion companion: half the readers would see the flat card and the other
 * half would see chrome on a tool whose credibility rests on restraint.
 */
export const CARD_LIFT_MOTION =
  "transition-[border-color,box-shadow,transform] duration-base ease-enter hover:-translate-y-px hover:border-foreground/25 hover:shadow-[0_2px_4px_hsl(var(--foreground)/0.04),0_12px_28px_hsl(var(--foreground)/0.10)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/25 motion-reduce:transition-none motion-reduce:hover:translate-y-0";

/**
 * The affordance inside a lifting card: the arrow that says it opens something.
 *
 * Along its own diagonal, a pixel each way — enough to read as a response, not enough to
 * reflow anything around it. Separate from the lift because it is on a child element and
 * keyed off the card's hover group.
 */
export const CARD_AFFORDANCE_MOTION =
  "transition-[transform,color] duration-base ease-enter group-hover:-translate-y-px group-hover:translate-x-px group-hover:text-foreground motion-reduce:transition-none motion-reduce:group-hover:translate-x-0 motion-reduce:group-hover:translate-y-0";

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

/**
 * The product header leaving on the way down and returning on the way up.
 *
 * A transform, so nothing reflows: the page does not shift under a reader's eyes when the
 * header goes. `duration-base` rather than `fast`, because this is a band the width of the
 * window and a quick slide of something that large reads as a flinch.
 *
 * The reduced-motion companion is that it never hides at all - see `nextHeaderVisibility`.
 * `transition-none` here as well, so a state change that arrives some other way, from a
 * keyboard focus or a resize, also arrives without animation.
 */
export const HEADER_SLIDE_MOTION =
  "transition-transform duration-base ease-enter motion-reduce:transition-none";
