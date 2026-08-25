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
  // tokens that Expert and Aligner used while Scout wrote `bg-emerald-500` and
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

test("the tone scale is declared once, and every tone has all three shapes", () => {
  // A signal appears as a dot, as a word, or as a filled chip, and nowhere else. A tone
  // missing one of the three is how a call site comes to reach for the palette again.
  const tone = FILES.find(({ relative }) => relative === TONE_SOURCE);
  if (!tone) throw new Error("lib/tone.ts is missing");
  for (const shape of ["TONE_DOT", "TONE_TEXT", "TONE_TINT"]) {
    assert.match(tone.text, new RegExp(`export const ${shape}: Record<Tone, string>`));
  }
  const source: string = tone.text;
  for (const name of ["success", "warning", "danger", "info", "neutral"]) {
    const shapes: number = source.split(new RegExp(`^  ${name}:`, "m")).length - 1;
    assert.equal(shapes, 3, `${name} is missing one of the three shapes`);
  }
});

test("nothing re-declares the tone scale", () => {
  const offenders = FILES.filter(
    ({ relative, text }) =>
      relative !== TONE_SOURCE && /export const TONE_(DOT|TEXT|TINT)\b/.test(text),
  ).map(({ relative }) => relative);
  assert.deepEqual(offenders, [], "a second tone scale defeats the point of having one");
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
