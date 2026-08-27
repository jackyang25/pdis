/**
 * The Gates Foundation's own values, and the one place they must not reach.
 *
 * Read from their published stylesheet by their token names, not from a screenshot:
 *
 *     --c-brand-primary-base   #f5f3ed  parchment   -> --background
 *     --c-brand-secondary-base #313a44  slate       -> --foreground, --primary, --ring
 *     --c-brand-tertiary       #ebcb00  yellow-50   -> --brand-accent, shell only
 *     --c-red-50               #d93027              -> --destructive, --tone-danger
 *     --c-gray-00..100         #f7f7f7 .. #0f0f0f   -> borders, fills, secondary text
 *     --font-sans              Noto Sans
 *     --font-serif             Noto Serif
 *
 * The load-bearing test here is the last one. Their brand yellow is `52 100% 46%`, and
 * `--tone-marked`, which means "a result cites this passage", is `45 93% 47%`. Seven degrees
 * apart. Their yellow beside a result is a citation, so it lives in the chrome or nowhere.
 */

import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import test from "node:test";

const WEB = path.resolve(import.meta.dirname, "..");
const read = (file: string) => readFileSync(path.join(WEB, file), "utf8");
const CSS = read("app/globals.css");

/** The value of one custom property in one appearance block. */
function token(name: string, appearance: "light" | "dark"): string {
  const block =
    appearance === "light"
      ? CSS.slice(CSS.indexOf(":root {"), CSS.indexOf(".dark {"))
      : CSS.slice(CSS.indexOf(".dark {"));
  const found = block.match(new RegExp(`--${name}:\\s*([^;]+);`));
  assert.ok(found, `--${name} is missing from the ${appearance} appearance`);
  return found[1].trim();
}

/** WCAG relative luminance, from an `H S% L%` triple. */
function luminance(hsl: string): number {
  const [h, s, l] = hsl.split(/\s+/).map((part) => Number(part.replace("%", "")));
  const a = (s / 100) * Math.min(l / 100, 1 - l / 100);
  const channel = (n: number) => {
    const k = (n + h / 30) % 12;
    const value = l / 100 - a * Math.max(-1, Math.min(k - 3, Math.min(9 - k, 1)));
    return value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * channel(0) + 0.7152 * channel(8) + 0.0722 * channel(4);
}

function contrast(first: string, second: string): number {
  const [a, b] = [luminance(first), luminance(second)];
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
}

test("their two faces are the ones loaded", () => {
  const layout = read("app/layout.tsx");
  assert.match(layout, /Noto_Sans/, "--font-sans is not their sans");
  assert.match(layout, /Noto_Serif/, "--font-display does not fall back to their serif");
  // Comment-stripped: the comment explaining the swap names the face it replaced.
  const code = layout.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
  assert.ok(!/\bInter\b/.test(code), "Inter is still loaded");
});

test("their sans carries the interface, not their serif", () => {
  // Their site sets body copy in Noto Serif, which reads at the sizes a marketing page uses
  // and not at the 10 and 11px most of a result is set in.
  const layout = read("app/layout.tsx");
  const sansBlock = layout.slice(layout.indexOf("const sans"), layout.indexOf("const display"));
  assert.match(sansBlock, /Noto_Sans/);
  const displayBlock = layout.slice(layout.indexOf("const display"));
  assert.match(displayBlock, /Noto_Serif/);
});

test("the brand values are theirs, in both appearances", () => {
  assert.equal(token("background", "light"), "45 29% 95%", "parchment");
  assert.equal(token("foreground", "light"), "212 16% 23%", "slate");
  assert.equal(token("primary", "light"), "212 16% 23%", "slate");
  assert.equal(token("ring", "light"), "212 16% 23%", "slate: their focus outline token");
  assert.equal(token("brand-accent", "light"), "52 100% 46%", "yellow-50");
  assert.equal(token("destructive", "light"), "3 70% 50%", "red-50");
  for (const appearance of ["light", "dark"] as const) {
    assert.ok(token("brand-accent", appearance), `no brand accent in ${appearance}`);
  }
});

test("the brand yellow never reaches a result", () => {
  // The whole reason it is a named token. Seven degrees from `--tone-marked`, so on or beside
  // a result it reads as "this passage is cited". `bg-brand` is allowed in the page shell,
  // which sits above every result and touches none of them.
  const SHELL = new Set(["components/app-shell.tsx"]);
  const offenders: string[] = [];
  const walk = (dir: string) => {
    for (const entry of readdirSync(path.join(WEB, dir), { withFileTypes: true })) {
      const next = `${dir}/${entry.name}`;
      if (entry.isDirectory()) walk(next);
      else if (entry.name.endsWith(".tsx") && !SHELL.has(next)) {
        if (/\b(?:bg|text|border|ring)-brand\b/.test(read(next))) offenders.push(next);
      }
    }
  };
  walk("app");
  walk("components");
  assert.deepEqual(
    offenders,
    [],
    "the brand accent is an interface colour; a result's colour is a judgment",
  );
});

test("the accent is legible where it is actually used", () => {
  // As a fill behind their own text colour, which is how their site uses it. Never as text:
  // 1.61:1 on white, unreadable at any size here.
  const onAccent = contrast(token("brand-accent", "light"), token("brand-accent-foreground", "light"));
  assert.ok(onAccent >= 4.5, `slate on their yellow is ${onAccent.toFixed(2)}:1`);
  const asText = contrast(token("brand-accent", "light"), token("card", "light"));
  assert.ok(
    asText < 3,
    "their yellow now passes as text, so this test no longer protects anything",
  );
});

test("every tone drawn as a mark clears 3:1 against the card", () => {
  // The tones were contrast-checked before the brand swap. `--card` and `--tone-danger` both
  // moved, so this re-checks rather than assuming.
  //
  // `marked` is not in the list, and finding that out corrected a claim in `globals.css`. It
  // is never a dot or a word: every use is a low-opacity wash behind a passage, where what has
  // to stay readable is the text on top, not the wash against the card. Held to 3:1 it is
  // 1.98, and always was. A saturated yellow cannot be both a legible mark and an unobtrusive
  // highlight, and highlight is the job it has.
  for (const appearance of ["light", "dark"] as const) {
    const card = token("card", appearance);
    for (const tone of ["info", "success", "warning", "danger", "external"]) {
      const ratio = contrast(token(`tone-${tone}`, appearance), card);
      assert.ok(
        ratio >= 3,
        `${appearance} --tone-${tone} is ${ratio.toFixed(2)}:1 against the card`,
      );
    }
  }
});

test("the citation wash stays a wash, and the text on it stays readable", () => {
  // At the opacity it is used, over a white card, with the passage's own colour on top.
  for (const appearance of ["light", "dark"] as const) {
    const card = luminance(token("card", appearance));
    const marked = luminance(token("tone-marked", appearance));
    // A 25% wash: the composite is the card mixed a quarter of the way to the tone.
    const composite = card + (marked - card) * 0.25;
    const foreground = luminance(token("foreground", appearance));
    const ratio =
      (Math.max(composite, foreground) + 0.05) / (Math.min(composite, foreground) + 0.05);
    assert.ok(
      ratio >= 4.5,
      `${appearance} body text on a citation wash is ${ratio.toFixed(2)}:1`,
    );
  }
});

test("body text clears 4.5:1 on the card and on the page ground", () => {
  for (const appearance of ["light", "dark"] as const) {
    for (const surface of ["card", "background"]) {
      const ratio = contrast(token("foreground", appearance), token(surface, appearance));
      assert.ok(ratio >= 4.5, `${appearance} foreground on ${surface} is ${ratio.toFixed(2)}:1`);
    }
    const muted = contrast(token("muted-foreground", appearance), token("card", appearance));
    assert.ok(muted >= 4.5, `${appearance} muted text is ${muted.toFixed(2)}:1`);
  }
});

test("the shell carries no palette colour of its own", () => {
  // It had two blurred shapes in indigo and cyan, which belonged to no palette and signalled
  // nothing. They were the app's only decorative colour.
  const code = read("components/app-shell.tsx")
    .replace(/\{\/\*[\s\S]*?\*\/\}/g, "")
    .replace(/\/\*[\s\S]*?\*\//g, "");
  assert.ok(!/indigo|cyan/.test(code), "the decorative blurs are back");
});

test("nothing tightens its letter-spacing", () => {
  // Fifteen overrides across seven values, a size-indexed ramp compensating for Inter's
  // generous default spacing at display sizes. Twelve of them were on an `h1`, `h2` or `h3`,
  // overriding the rule `globals.css` already sets for the display face.
  //
  // Both faces are theirs now. Noto Serif is spaced for reading, so tightening closes the gaps
  // its serifs hold open; Noto Sans carries 10 and 11px text where it is drawn to be legible
  // and tightening costs that. The correct value is the font's own, so any class here is an
  // override of it.
  const offenders: string[] = [];
  const walk = (dir: string) => {
    for (const entry of readdirSync(path.join(WEB, dir), { withFileTypes: true })) {
      const next = `${dir}/${entry.name}`;
      if (entry.isDirectory()) walk(next);
      else if (entry.name.endsWith(".tsx")) {
        const found = read(next).match(/tracking-(?:tight(?:er)?|\[-[\d.]+em\])/g);
        if (found) offenders.push(`${next}: ${[...new Set(found)].join(", ")}`);
      }
    }
  };
  walk("app");
  walk("components");
  assert.deepEqual(offenders, [], "let the face use its own spacing");
});

test("the display face is not tightened", () => {
  // Its spacing travels with the face, in the recipe, rather than in a stylesheet rule keyed on
  // a tag: the two have to move together, and they did not when the face changed.
  const typography = read("lib/typography.ts");
  const recipe = typography.match(/export const DISPLAY_HEADING = "([^"]+)"/);
  assert.ok(recipe, "DISPLAY_HEADING is missing");
  assert.match(recipe[1], /font-display/);
  assert.ok(
    !/tracking-(?:tight|tighter|\[-)/.test(recipe[1]),
    `the titling face is tightened by ${recipe[1]}, which a serif does not want`,
  );
});

test("no Inter-only OpenType feature is still requested", () => {
  // `ss01` and `cv11` were Inter's alternate glyph sets. Left in place they either do nothing
  // or, if the new face defines those slots, substitute glyphs nobody chose.
  // Comment-stripped: the comment explaining the removal names the features it removed.
  const declarations = CSS.replace(/\/\*[\s\S]*?\*\//g, "");
  assert.ok(!/ss01|cv11/.test(declarations), "an Inter alternate set is still requested");
  assert.match(CSS, /font-feature-settings:\s*"rlig" 1, "calt" 1/);
});

test("the serif titles something; the sans labels something", () => {
  // The tag rule got this wrong in both directions. `h1, h2, h3 { font-family: display }` was
  // invisible while the display face was Inter Tight, a sans, and became a hundred unexamined
  // decisions the moment it became a serif: twelve `sm` and `xs` headings that label a row
  // inside a result, and two eyebrows - a 10px uppercase label set in a serif.
  //
  // A tag does not say what a heading is doing. `h3` is a 17px tool card title in one place
  // and a 14px field label in another; `h2` is used for an eyebrow in two.
  const declarations = CSS.replace(/\/\*[\s\S]*?\*\//g, "");
  assert.ok(
    !/\bh1,\s*\n?\s*h2,\s*\n?\s*h3\s*\{[^}]*font-family/.test(declarations),
    "the display face is keyed on the tag again",
  );

  // Only through the recipe, so where the serif goes is one list.
  const offenders: string[] = [];
  const walk = (dir: string) => {
    for (const entry of readdirSync(path.join(WEB, dir), { withFileTypes: true })) {
      const next = `${dir}/${entry.name}`;
      if (entry.isDirectory()) walk(next);
      else if (entry.name.endsWith(".tsx")) {
        const text = read(next);
        // Two exemptions, each for a reason the recipe cannot serve. `app-shell` sets the
        // wordmark, which is a mark rather than a heading. `layout` declares the CSS variable
        // the recipe resolves to, so the string appears there by definition.
        if (next === "components/app-shell.tsx" || next === "app/layout.tsx") continue;
        for (const [index, line] of text.split("\n").entries()) {
          if (!/\bfont-display\b/.test(line)) continue;
          if (line.includes("DISPLAY_HEADING")) continue;
          offenders.push(`${next}:${index + 1}`);
        }
      }
    }
  };
  walk("app");
  walk("components");
  assert.deepEqual(offenders, [], "import DISPLAY_HEADING from lib/typography.ts");
});

test("no heading that labels a row is set in the serif", () => {
  // The break falls at about 15px, which is the point below which a heading in this interface
  // is labelling rather than titling. A `text-sm` or smaller heading carrying the recipe would
  // mean the rule moved without the reasoning.
  const offenders: string[] = [];
  const walk = (dir: string) => {
    for (const entry of readdirSync(path.join(WEB, dir), { withFileTypes: true })) {
      const next = `${dir}/${entry.name}`;
      if (entry.isDirectory()) walk(next);
      else if (entry.name.endsWith(".tsx")) {
        read(next)
          .split("\n")
          .forEach((line, index) => {
            if (!line.includes("DISPLAY_HEADING")) return;
            if (/text-(?:xs|sm|\[1[0-4]px\]|\[[0-9]px\])/.test(line)) {
              offenders.push(`${next}:${index + 1}`);
            }
          });
      }
    }
  };
  walk("app");
  walk("components");
  assert.deepEqual(offenders, [], "a heading at a labelling size is set in the titling face");
});

test("an eyebrow is never in the serif", () => {
  // Two were, because they are written as `<Label asChild><h2>` and the tag rule reached them.
  // A 10px uppercase label in a serif is the clearest case of the rule being wrong rather than
  // debatable.
  const label = read("components/ui/label.tsx");
  assert.match(label, /EYEBROW/, "the shared Label no longer uses the eyebrow shape");
  assert.ok(!/font-display|DISPLAY_HEADING/.test(label), "the eyebrow is set in the serif");
});

test("a card's edge is visible, and an input's edge is more so", () => {
  // The border was 1.28:1 against the white card it encloses, while a card is only 1.10:1
  // against the ground it sits on. So the border was doing nearly all the work of separating
  // the two, at a contrast where it could barely be seen. Darker rather than thicker: a 2px
  // line at 1.28:1 is still 1.28:1, and reads as blurred rather than defined.
  //
  // The second half is the relationship the two tokens have always had, and darkening the
  // border alone collapsed them onto one value. An input is a thing you type into, so its edge
  // reads as more defined than the edge of a card.
  for (const appearance of ["light", "dark"] as const) {
    const card = token("card", appearance);
    const border = contrast(token("border", appearance), card);
    const input = contrast(token("input", appearance), card);
    assert.ok(border >= 1.5, `${appearance} border is ${border.toFixed(2)}:1 against the card`);
    assert.ok(
      input > border,
      `${appearance} input (${input.toFixed(2)}) is not firmer than the border (${border.toFixed(2)})`,
    );
  }
});

test("the border does its work by tone, not by width", () => {
  // A thicker pale line is a wider pale line. Nothing in the app draws a 2px neutral edge.
  const offenders: string[] = [];
  const walk = (dir: string) => {
    for (const entry of readdirSync(path.join(WEB, dir), { withFileTypes: true })) {
      const next = `${dir}/${entry.name}`;
      if (entry.isDirectory()) walk(next);
      else if (entry.name.endsWith(".tsx")) {
        // `border-2` only: an edge thickened on every side, which is what a card or a panel
        // has. `border-l-2` is the quotation shape and a different idiom entirely, owned by
        // `evidence-text.test.ts`.
        //
        // The first version of this pattern was `border-(?:[trb]|[xy])?-2`, which required a
        // side segment and so never matched the plain `border-2` it exists to catch. Found by
        // planting one and watching nothing fail.
        const found = read(next).match(/\bborder-2\b/g);
        if (found) offenders.push(next);
      }
    }
  };
  walk("app");
  walk("components");
  assert.deepEqual(offenders, [], "a border is being thickened where it should be darkened");
});

test("every text colour is in one family, and every surface in another", () => {
  // Their system has one text colour, `--c-text-base: var(--c-slate)`, and a fully desaturated
  // ramp for everything else. Ours follows: text is slate, surfaces and edges are neutral.
  //
  // Secondary text was the exception, set from their gray-60 by hand while the dark appearance
  // had already been moved into the slate family wholesale. So one token was in two families
  // depending on the appearance, and in the light one a paragraph's body and its secondary line
  // sat in two temperatures.
  const TEXT = [
    "foreground",
    "card-foreground",
    "muted-foreground",
    "primary",
    "secondary-foreground",
    "accent-foreground",
  ];
  const SURFACE = ["card", "secondary", "muted", "accent", "border", "input"];

  const hue = (name: string, appearance: "light" | "dark") =>
    Number(token(name, appearance).split(/\s+/)[0]);
  const saturation = (name: string, appearance: "light" | "dark") =>
    Number(token(name, appearance).split(/\s+/)[1].replace("%", ""));

  // Slate is 212. A text colour outside that family reads at a different temperature from the
  // copy beside it.
  for (const name of TEXT) {
    const light = hue(name, "light");
    assert.ok(
      Math.abs(light - 212) <= 6 || saturation(name, "light") === 0,
      `light --${name} is at hue ${light}, outside the slate family`,
    );
  }
  // A pure-white or pure-black text token is allowed: it has no family.
  for (const name of TEXT) {
    if (saturation(name, "light") === 0) {
      const lightness = Number(token(name, "light").split(/\s+/)[2].replace("%", ""));
      assert.ok(
        lightness >= 97 || lightness <= 3,
        `light --${name} is a neutral grey, so it is a text colour outside the family`,
      );
    }
  }
  // Surfaces and edges stay out of it, so the two axes cannot be confused.
  for (const name of SURFACE) {
    assert.equal(
      saturation(name, "light"),
      0,
      `light --${name} carries a hue; surfaces are the neutral ramp`,
    );
  }
});
