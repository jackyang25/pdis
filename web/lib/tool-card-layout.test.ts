/**
 * A tool card's height and its footer, guarded against drifting apart again.
 *
 * The cards carried three floors: 176px for a PST tool, 150px for a shared utility, 192px for
 * an external workflow. Only the 150 matched its content. The other two were sized when a card's mark
 * had a row to itself and its footer carried a second label beside the duration; both were
 * removed, the floors came down but not to the content, and because `mt-auto` pushes the
 * footer to the bottom, every leftover pixel pooled in one gap. A card sat 25px above what it
 * contained, all of it between the description and the duration.
 *
 * One floor now: every card holds the same footer, a single line of text. The external
 * workflow cards, whose footer was a row of 32px chips and needed a taller floor, were removed.
 *
 * The footers had also drifted to opposite edges of the same slot, a duration pushed right by
 * a `justify-end` that outlived the label it was holding it away from.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";

const PAGE = path.join(path.resolve(import.meta.dirname, ".."), "app/page.tsx");

/**
 * The file without its comments.
 *
 * Every one of these rules names the thing it forbids, and the reason it forbids it, in a
 * comment in the file it checks. Reading the file raw, each rule finds its own explanation and
 * fails.
 */
const source = readFileSync(PAGE, "utf8")
  .replace(/\/\*[\s\S]*?\*\//g, "")
  .replace(/^\s*\/\/.*$/gm, "");

function floor(name: string): number {
  const match = source.match(new RegExp(`const ${name} = "min-h-\\[(\\d+)px\\]"`));
  assert.ok(match, `${name} is not declared as a single min-height`);
  return Number(match[1]);
}

test("a card's height comes from a named floor, never an inline one", () => {
  const declared = [...source.matchAll(/const \w+ = "min-h-\[\d+px\]";/g)].length;
  const used = [...source.matchAll(/min-h-\[\d+px\]/g)].length;
  assert.equal(
    used,
    declared,
    "a min-height was written into a class string; the floors are named constants so the "
      + "arithmetic behind them stays with them",
  );
});

test("every card shares one floor", () => {
  assert.equal(floor("CARD_FLOOR"), 146);
  assert.equal([...source.matchAll(/const \w+ = "min-h-\[\d+px\]";/g)].length, 1);
});

test("every section's cards share one floor", () => {
  const sections = readFileSync(path.join(path.dirname(PAGE), "../lib/tool-sections.ts"), "utf8");
  assert.ok(
    !/compact/.test(sections),
    "a section asked for shorter cards; the same card with the same content had two heights, "
      + "and the shorter one was simply the correct one",
  );
});

test("the footer starts where the rest of the card starts", () => {
  assert.ok(!/justify-end|text-right|items-end/.test(source), "a footer is aligned to the far edge");
});

test("the card holds its footer in one slot", () => {
  const footers = [...source.matchAll(/mt-auto pt-(\d+)/g)];
  assert.equal(footers.length, 1);
});

test("the duration is styled as a count, not as a local size", () => {
  assert.match(source, /className=\{COUNT\}/);
  assert.ok(
    !/muted-foreground\/80/.test(source),
    "the duration carried a tone nothing else on the page used",
  );
});
