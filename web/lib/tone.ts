/**
 * The one scale a result signal is painted on.
 *
 * Six tokens exist in `globals.css`, themed and contrast-checked for both colour schemes.
 * Only `danger` was actually reached through them everywhere; `success` and `warning` were
 * written as raw palette classes in two tools:
 *
 *   Screener, Aligner   bg-[hsl(var(--tone-success))]      the token
 *   Scout             bg-emerald-500, bg-amber-400       the palette, 18 times
 *   Inspector         bg-emerald-500/10 text-emerald-700 the palette, with a hand-written
 *                                                        dark: variant beside it
 *
 * That is one judgement painted three ways, and in Scout's case **none of the eighteen
 * carried a dark-mode variant**, so a verdict that reads at one contrast in light mode read
 * at another in dark. A token cannot have that problem: the theme swaps underneath it.
 *
 * Three shapes, because a signal appears in three places and nowhere else:
 *
 *   TONE_DOT    the dot beside a verdict
 *   TONE_TEXT   the verdict word itself
 *   TONE_TINT   a filled chip or cell, background and text together
 *
 * **Which shape, and when.** The list above says where each one goes and, for a long time,
 * nothing said which situation calls for which — so four tools each picked one and a
 * reader moving between them met one idea in four costumes. The rule is how many signals
 * share the row:
 *
 *   one signal, and it is what the row is about        TINT. It has to be findable while
 *                                                      scanning a column of rows.
 *   several signals in one row, none of them dominant  DOT. A tint on each turns the row
 *                                                      into a bar chart of colour, and
 *                                                      the reader is comparing counts,
 *                                                      not hunting for one verdict.
 *   the verdict is the sentence                        TEXT.
 *
 * A count row is always the second case, which is what `ui/verdict-counts` renders.
 *
 * `neutral` is the absence of a signal, not a fourth verdict. It is deliberately quieter
 * than the others so "unknown" cannot be mistaken for a reading.
 */

export type Tone = "success" | "warning" | "danger" | "info" | "neutral";

/** The dot beside a verdict. */
export const TONE_DOT: Record<Tone, string> = {
  success: "bg-[hsl(var(--tone-success))]",
  warning: "bg-[hsl(var(--tone-warning))]",
  danger: "bg-[hsl(var(--tone-danger))]",
  info: "bg-[hsl(var(--tone-info))]",
  // Not `--tone-neutral`. Nothing is being signalled, so this is the muted foreground the
  // rest of the interface uses for absence, at the weight a dot needs to stay a dot.
  neutral: "bg-muted-foreground/40",
};

/**
 * The same tone as a colour value, for a surface that cannot take a class.
 *
 * SVG strokes, essentially: the evidence map draws its edges as `stroke` attributes. It
 * exists so a canvas and the text beside it cannot disagree about what `warning` looks
 * like, which they did while the map held its own copy of these five values.
 */
export const TONE_STROKE: Record<Tone, string> = {
  success: "hsl(var(--tone-success))",
  warning: "hsl(var(--tone-warning))",
  danger: "hsl(var(--tone-danger))",
  info: "hsl(var(--tone-info))",
  neutral: "hsl(var(--muted-foreground))",
};

/** The verdict word itself. */
export const TONE_TEXT: Record<Tone, string> = {
  success: "text-[hsl(var(--tone-success))]",
  warning: "text-[hsl(var(--tone-warning))]",
  danger: "text-[hsl(var(--tone-danger))]",
  info: "text-[hsl(var(--tone-info))]",
  neutral: "text-muted-foreground",
};

/**
 * A filled chip or table cell.
 *
 * The tint is 10%, one value rather than a choice per call site: Inspector filled at 10%
 * and the coverage strip filled solid, so the same verdict was a wash in one tool and a
 * block in another.
 */
export const TONE_TINT: Record<Tone, string> = {
  success: "bg-[hsl(var(--tone-success))]/10 text-[hsl(var(--tone-success))]",
  warning: "bg-[hsl(var(--tone-warning))]/10 text-[hsl(var(--tone-warning))]",
  danger: "bg-[hsl(var(--tone-danger))]/10 text-[hsl(var(--tone-danger))]",
  info: "bg-[hsl(var(--tone-info))]/10 text-[hsl(var(--tone-info))]",
  neutral: "bg-muted text-muted-foreground",
};
