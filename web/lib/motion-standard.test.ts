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

test("failure signals use the danger tone, never a raw red", () => {
  // Grade F, `unsupported`, `contradicts`, `unfavorable`, and `conflict` are the
  // same judgement in four tools, so they share one themed, contrast-checked
  // token. `text-destructive` stays for system errors, which are a different
  // thing from a bad result.
  const offenders = FILES.filter(({ text }) => /-red-\d{2,3}/.test(text)).map(
    ({ relative }) => relative,
  );
  assert.deepEqual(
    offenders,
    [],
    "use hsl(var(--tone-danger)) for a negative signal, or text-destructive for an error",
  );
});
