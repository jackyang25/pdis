/**
 * Enforces the motion standard so it cannot drift.
 *
 * A convention people remember decays; these checks fail the build instead.
 * If a rule here is wrong, change the rule deliberately — do not add an
 * exception to get a commit through.
 */

import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import test from "node:test";

const ROOT = path.resolve(import.meta.dirname, "..");
const SCANNED = ["app", "components", "lib"];

/** The skeleton primitive owns the shimmer; nothing else may animate a wait. */
const SHIMMER_OWNER = path.join("components", "ui", "skeleton.tsx");
/** Motion recipes are declared here, so this file states durations directly. */
const MOTION_SOURCE = path.join("lib", "motion.ts");
/** The surface scale is declared here, so this file states its class strings directly. */
const SURFACE_SOURCE = path.join("lib", "surface.ts");

/** The text recipes are declared here, so this file states their class strings directly. */
const TYPOGRAPHY_SOURCE = path.join("lib", "typography.ts");

/** The tone scale is declared here, so this file states its class strings directly. */
const TONE_SOURCE = path.join("lib", "tone.ts");

/**
 * Files allowed a palette colour, and why.
 *
 * The rule is about *result signals*: a verdict, a grade, a status. Decoration is not one,
 * and giving the page's background wash a semantic token would say a judgement is being made
 * where none is.
 */
const PALETTE_EXEMPT: Record<string, string> = {
  [path.join("components", "app-shell.tsx")]:
    "two blurred background shapes behind the page, which signal nothing",
};

function sourceFiles(): string[] {
  const out: string[] = [];
  const walk = (dir: string) => {
    for (const entry of readdirSync(dir)) {
      const full = path.join(dir, entry);
      if (statSync(full).isDirectory()) {
        walk(full);
        continue;
      }
      if (/\.tsx?$/.test(entry) && !/\.test\.tsx?$/.test(entry)) out.push(full);
    }
  };
  for (const dir of SCANNED) walk(path.join(ROOT, dir));
  return out;
}

const FILES = sourceFiles().map((file) => ({
  relative: path.relative(ROOT, file),
  text: readFileSync(file, "utf8"),
}));

test("motion uses duration tokens, never raw milliseconds", () => {
  const offenders = FILES.flatMap(({ relative, text }) =>
    [...text.matchAll(/\bduration-\[?\d+m?s?\]?/g)].map(
      (match) => `${relative}: ${match[0]}`,
    ),
  );
  assert.deepEqual(
    offenders,
    [],
    "use duration-fast, duration-base, or duration-slow from tailwind.config.ts",
  );
});

/**
 * A spinner is exempt: its movement *is* the status, so stopping it under
 * reduced motion would remove the only signal that work is in progress. WCAG
 * asks for movement that is decorative or distracting to be suppressible, not
 * for progress indicators to be silenced.
 */
const STATUS_INDICATOR = /\banimate-spin\b/;

test("every transition and animation has a reduced-motion companion", () => {
  const offenders: string[] = [];
  for (const { relative, text } of FILES) {
    if (relative === MOTION_SOURCE) continue;
    // Class strings are the unit of review: a string carrying motion must also
    // carry its opt-out, because that is what ships to the element.
    for (const [literal] of text.matchAll(/"[^"\n]*\b(?:transition|animate)-[^"\n]*"/g)) {
      const hasMotion =
        /\b(?:transition|animate)-(?!none\b)/.test(literal) &&
        !STATUS_INDICATOR.test(literal);
      const opted =
        /motion-reduce:/.test(literal) ||
        /\b(?:transition|animate)-none\b/.test(literal);
      if (hasMotion && !opted) offenders.push(`${relative}: ${literal.slice(0, 72)}`);
    }
  }
  assert.deepEqual(
    offenders,
    [],
    "add motion-reduce:transition-none or motion-reduce:animate-none, or import a recipe from lib/motion.ts",
  );
});

test("only the skeleton primitive animates a wait with a shimmer or pulse", () => {
  const offenders = FILES.filter(
    ({ relative, text }) =>
      relative !== SHIMMER_OWNER &&
      relative !== MOTION_SOURCE &&
      /animate-(?:shimmer|pulse)/.test(text),
  ).map(({ relative }) => relative);
  assert.deepEqual(
    offenders,
    [],
    "render <Skeleton /> instead of animating a placeholder in place",
  );
});

test("every motion recipe carries its own reduced-motion companion", () => {
  /*
    `lib/motion.ts` is exempt from the check above, so that it can state durations
    directly — and that exemption let a recipe ship without an opt-out, which is the worst
    place for one to be missing: a recipe is reused everywhere by definition. Found by
    deleting the companion from `CARD_LIFT_MOTION` and watching nothing fail.

    `STREAM_CARET_MOTION` is the one exception and is meant to be: like a spinner, its
    movement *is* the status, so stopping it would remove the only signal that generation
    is still going.
  */
  const motion = FILES.find(({ relative }) => relative === MOTION_SOURCE);
  assert.ok(motion, "lib/motion.ts is missing");

  const offenders: string[] = [];
  for (const [, name, value] of motion.text.matchAll(
    /export const (\w+)\s*(?:=|:[^=]*=)\s*((?:"[^"]*"\s*\+?\s*)+);/g,
  )) {
    if (name === "STREAM_CARET_MOTION") continue;
    if (!/\b(?:transition|animate)-(?!none\b)/.test(value)) continue;
    if (!/motion-reduce:/.test(value)) offenders.push(name);
  }
  assert.deepEqual(
    offenders,
    [],
    "a recipe every surface imports must say what it does under reduced motion",
  );
});

test("every motion recipe has a consumer", () => {
  const motion = FILES.find(({ relative }) => relative === MOTION_SOURCE);
  assert.ok(motion, "lib/motion.ts is missing");
  const recipes = [...motion.text.matchAll(/export const (\w+)/g)].map(
    (match) => match[1],
  );
  assert.ok(recipes.length > 0, "no recipes are declared");
  const unused = recipes.filter(
    (recipe) =>
      !FILES.some(
        ({ relative, text }) =>
          relative !== MOTION_SOURCE && text.includes(recipe),
      ),
  );
  // A recipe nothing imports is dead code that still reads as a standard, which
  // is worse than no recipe at all.
  assert.deepEqual(unused, [], "delete the recipe or apply it where it belongs");
});

test("the arrival highlight is imported, never written inline", () => {
  // Three tools jump into one document trace, and the ring is what tells a reader
  // which block answered. Written inline it would eventually differ per tool: a
  // different tone, a different hold, or none at all where the jump feels obvious to
  // whoever added it. The inset foreground ring is the recipe's signature: inset
  // because a row's paint containment clips anything drawn outside it, and foreground
  // because every tone already means a judgement about the passage.
  const offenders = FILES.filter(
    ({ relative, text }) =>
      relative !== MOTION_SOURCE && /ring-inset ring-foreground/.test(text),
  ).map(({ relative }) => relative);
  assert.deepEqual(
    offenders,
    [],
    "import ARRIVAL_HIGHLIGHT from lib/motion.ts instead of restyling the jump",
  );
});

test("a jump holds for the standard duration, not a hand-picked one", () => {
  // The class carries the ring, a timeout carries how long it stays: half the signal
  // lives in JavaScript, where no class-name rule can see it.
  const offenders = FILES.filter(
    ({ relative, text }) =>
      relative !== MOTION_SOURCE
      && /setTimeout\([^)]*,\s*\d{3,}\s*\)/.test(text.replace(/\s+/g, " ")),
  ).map(({ relative }) => relative);
  assert.deepEqual(
    offenders,
    [],
    "hold a highlight for ARRIVAL_HIGHLIGHT_MS from lib/motion.ts",
  );
});

test("a result signal uses a tone token, never a raw palette colour", () => {
  // Grade F, `unsupported`, `contradicts`, `unfavorable`, and `conflict` are the same
  // judgement in four tools, so they share one themed, contrast-checked token.
  // `text-destructive` stays for system errors, which are a different thing from a bad
  // result.
  //
  // This covered red alone for a long time, and the gap showed: `success` and `warning` had
  // tokens that Screener and Aligner used while Scout wrote `bg-emerald-500` and
  // `bg-amber-400` eighteen times and Inspector wrote the palette with a hand-kept `dark:`
  // variant beside it. **None of Scout's eighteen had a dark-mode variant at all**, so a
  // verdict that read at one contrast in light mode read at another in dark. A token cannot
  // have that problem: the theme swaps underneath it.
  const PALETTE = /-(?:red|green|emerald|amber|yellow|orange|blue|sky|indigo|violet|purple|pink|rose|teal|cyan|lime)-\d{2,3}\b/;
  const offenders = FILES.filter(
    ({ relative, text }) =>
      relative !== TONE_SOURCE && !PALETTE_EXEMPT[relative] && PALETTE.test(text),
  ).map(({ relative }) => relative);
  assert.deepEqual(
    offenders,
    [],
    "use TONE_DOT, TONE_TEXT or TONE_TINT from lib/tone.ts, or text-destructive for an error",
  );
});

/**
 * The four forms one tone takes. A signal appears as a dot, a word, a filled chip, or -
 * where the surface cannot take a class at all - a raw colour value for an SVG stroke.
 * A tone missing one of the four is how a call site comes to reach for the palette again,
 * which is what the evidence map did: it needed a stroke, found none, and wrote out all
 * five colours beside a private tone scale named after the colours themselves.
 */
const TONE_SHAPES = ["TONE_DOT", "TONE_TEXT", "TONE_TINT", "TONE_STROKE"];

test("the tone scale is declared once, and every tone has all four shapes", () => {
  const tone = FILES.find(({ relative }) => relative === TONE_SOURCE);
  if (!tone) throw new Error("lib/tone.ts is missing");
  for (const shape of TONE_SHAPES) {
    assert.match(tone.text, new RegExp(`export const ${shape}: Record<Tone, string>`));
  }
  const source: string = tone.text;
  for (const name of ["success", "warning", "danger", "info", "neutral"]) {
    const shapes: number = source.split(new RegExp(`^  ${name}:`, "m")).length - 1;
    assert.equal(shapes, TONE_SHAPES.length, `${name} is missing one of the four shapes`);
  }
});

test("nothing re-declares the tone scale", () => {
  const offenders = FILES.filter(
    ({ relative, text }) =>
      relative !== TONE_SOURCE &&
      /export const TONE_(DOT|TEXT|TINT|STROKE)\b/.test(text),
  ).map(({ relative }) => relative);
  assert.deepEqual(offenders, [], "a second tone scale defeats the point of having one");
});

test("no surface names a tone after its colour", () => {
  // `EvidenceMapSignalTone` was `green | blue | amber | red | neutral` - the shared scale
  // with the meanings replaced by the colours they happen to render as. It is the one
  // rename that cannot be reconciled with anything: a reader cannot tell whether `blue`
  // agrees with `info`, and the map's `neutral` had in fact drifted to a different colour
  // from every other neutral in the interface.
  //
  // The scale is `success | warning | danger | info | neutral` because those are readings.
  // A palette that says what a thing means survives a change of palette.
  const offenders = FILES.filter(({ text }) =>
    /\b(?:tone|Tone)\b[^\n]*=\s*"(?:green|blue|amber|red|orange|yellow)"/.test(text)
    || /^\s*\|\s*"(?:green|blue|amber|red)"$/m.test(text),
  ).map(({ relative }) => relative);
  assert.deepEqual(offenders, [], "a tone named after a colour is a second scale");
});

test("an eyebrow label is one shape, not a letter-spacing per author", () => {
  // The audit that produced `lib/typography.ts`: this label appeared 36 times across five
  // letter-spacings (`tracking-wide`, `[0.08em]`, `[0.1em]`, `[0.12em]`, `[0.14em]`) and two
  // weights. Nothing distinguished them; they are the same label doing the same job in a
  // panel header, a definition list, a table column and a form field.
  const offenders = FILES.filter(
    ({ relative, text }) =>
      relative !== TYPOGRAPHY_SOURCE && /text-\[10px\][^"`]*\buppercase\b/.test(text),
  ).map(({ relative }) => relative);
  assert.deepEqual(offenders, [], "import EYEBROW from lib/typography.ts");
});

test("a count is tabular wherever it is written", () => {
  // A column of counts that do not line up is harder to scan than no column. Ten files wrote
  // this out and one of them at a size larger than the rest.
  const source = FILES.find(({ relative }) => relative === TYPOGRAPHY_SOURCE);
  if (!source) throw new Error("lib/typography.ts is missing");
  assert.match(source.text, /export const EYEBROW =/);
  assert.match(source.text, /export const COUNT =/);
  assert.match(source.text, /tabular-nums/);
});

test("a tinted surface is one of the five the scale names", () => {
  // Twelve values of one tint were in use: `bg-muted` and eleven opacities from /10 to /70.
  // A header band was /10, /15, /30 and /35 in four places; hovering a row was one of seven
  // values; a selected row was /45, /50 or /70. None of the rungs meant anything.
  //
  // The values rather than the constant, because Tailwind reads class names literally out of
  // the source: a call site has to write `bg-muted/15`, so what can be checked is that the
  // number it wrote is one the scale sanctions.
  const SANCTIONED = new Set([
    "bg-muted",                 // FILL: a solid track or placeholder
    "bg-foreground/[0.025]",    // OPEN.body: everything a summary revealed
    "bg-foreground/[0.045]",    // RECESSED, and HOVER at the same weight
    "bg-foreground/[0.07]",     // OPEN.header, and SELECTED at the same weight
  ]);
  const offenders: string[] = [];
  for (const { relative, text } of FILES) {
    if (relative === SURFACE_SOURCE) continue;
    // A *tint* is what this scale owns: a low alpha of the foreground, laid over content.
    // A solid or near-solid `bg-foreground` is ink - a plot point, a progress bar, a caret -
    // and belongs to whatever is drawing it. The line between them is 10%: below it nothing
    // is legible as an object, above it nothing is legible as a wash.
    for (const match of text.matchAll(/bg-(?:muted|foreground)(?:\/(?:\[[\d.]+\]|\d+))?/g)) {
      const alpha = match[0].match(/\/\[?([\d.]+)\]?$/)?.[1];
      // A percentage form like `/50` is a percent; a bracket form like `/[0.045]` is a
      // fraction. Both become a fraction here so one threshold can decide.
      const fraction = alpha == null ? 1 : alpha.includes(".") ? Number(alpha) : Number(alpha) / 100;
      if (match[0].startsWith("bg-foreground") && fraction >= 0.1) continue;
      if (!SANCTIONED.has(match[0])) offenders.push(`${relative}: ${match[0]}`);
    }
  }
  assert.deepEqual([...new Set(offenders)], [], "use a value lib/surface.ts names");
});

test("an open row is tinted for its whole height, not just its summary", () => {
  // The reason the scale exists. Only the summary carried a tint, so an open row marked
  // where it began and never where it ended: scrolling into a long body left no signal that
  // you were still inside one.
  const surface = FILES.find(({ relative }) => relative === SURFACE_SOURCE);
  if (!surface) throw new Error("lib/surface.ts is missing");
  assert.match(surface.text, /header: "group-open\/expand:bg-foreground\/\[0\.07\]"/);
  assert.match(surface.text, /body: "bg-foreground\/\[0\.025\]"/);
  // The tint is the foreground, not `--muted`. `--muted` is 96% lightness, so every alpha of
  // it lands within four points of white and the first version of this scale was invisible.
  assert.ok(
    !/bg-muted\/\d/.test(surface.text),
    "the scale is back on an almost-white base, where its rungs cannot be told apart",
  );

  const page = FILES.find(({ relative }) => relative === path.join("app", "scout", "page.tsx"));
  if (!page) throw new Error("the scout page is missing");
  // Counted against each other rather than against a number. The literal said 4, and when
  // a row was deleted the test failed for having the wrong tally rather than for anything
  // being untinted - a count has to be re-agreed every time the page changes, while the
  // rule does not. One body tint per expandable row is the rule.
  const rows = [...page.text.matchAll(/summary className=\{(?:cn\()?EXPANDABLE_ROW/g)];
  const bodies = [...page.text.matchAll(/SURFACE\.open\.body/g)];
  assert.ok(rows.length > 0, "no expandable rows found; the selector has drifted");
  assert.equal(
    bodies.length,
    rows.length,
    `${rows.length} expandable rows but ${bodies.length} tinted bodies: `
      + "a row is tinting only its summary again",
  );
});
