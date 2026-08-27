/**
 * The card meta row answers one question: can I run this before my next meeting?
 *
 * That only works if every card answers it the same way. The field is a free
 * string, so nothing structural stops the next tool from adding a fourth shape —
 * it already held ranges, bare numbers, and "On demand" at once, and a reader
 * comparing two cards could not tell whether "2 min" and "3–5 min" were measured
 * the same way.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";

import { EXTERNAL_TOOLS, WORKSPACE_TOOLS } from "./tools.ts";

/**
 * Approximate minutes, rounded to what a reader should budget.
 *
 * "approx." rather than a tilde. Beside a duration the tilde reads as a maths operator, and
 * these sit in a card next to a capability rather than in an expression. One form for all of
 * them, so the estimates read as one scale.
 */
const DURATION = /^approx\. \d+ min$/;

test("every available workspace tool states how long a run takes", () => {
  const available = WORKSPACE_TOOLS.filter((tool) => tool.availability === "available");
  assert.ok(available.length > 0, "no available workspace tools were found");
  for (const tool of available) {
    assert.match(
      tool.activity ?? "",
      DURATION,
      `${tool.id} publishes "${tool.activity}", which a reader cannot compare with `
        + `"approx. 5 min". Estimates are approximate minutes, so they read as one scale.`,
    );
  }
});

test("a tool that is not built yet claims no runtime", () => {
  // Not a gap to fill: there is nothing to have timed. Publishing a number for
  // unbuilt work would be the only unmeasured figure on the page.
  for (const tool of WORKSPACE_TOOLS) {
    if (tool.availability === "available") continue;
    assert.equal(
      tool.activity,
      undefined,
      `${tool.id} is ${tool.availability} but publishes a runtime`,
    );
  }
});

test("the estimate is a budget, so it rounds up rather than to the middle", () => {
  // Pinned by example: a reader who set aside the stated time and waited longer
  // is worse served than one who finished early, so these came from observed
  // upper ends rather than averages.
  const scout = WORKSPACE_TOOLS.find((tool) => tool.id === "scout");
  // "approx." rather than a tilde: beside a duration the tilde reads as a maths operator,
  // and this sits in a card next to a capability, not in an expression.
  assert.equal(scout?.activity, "approx. 20 min");
});

test("an available external tool offers somewhere to go", () => {
  // The stage gate evaluator sat as coming_soon with an empty shortcut list.
  // Marking one available without a link would render a card that says it is
  // ready and gives no way to reach it.
  for (const tool of EXTERNAL_TOOLS) {
    if (tool.availability !== "available") continue;
    assert.ok(
      tool.shortcuts.length > 0,
      `${tool.id} is available but links nowhere`,
    );
  }
});

test("a tool that is not built yet links nowhere", () => {
  for (const tool of EXTERNAL_TOOLS) {
    if (tool.availability === "available") continue;
    assert.equal(
      tool.shortcuts.length,
      0,
      `${tool.id} is ${tool.availability} but offers a link`,
    );
  }
});

test("every shortcut points at the provider it names", () => {
  // A mislabelled link sends someone to the wrong assistant, which looks like
  // the tool being broken rather than the label being wrong.
  const host: Record<string, string> = {
    ChatGPT: "chatgpt.com",
    Claude: "claude.ai",
  };
  for (const tool of EXTERNAL_TOOLS) {
    for (const shortcut of tool.shortcuts) {
      assert.ok(
        shortcut.url.includes(host[shortcut.label]),
        `${tool.id}: a ${shortcut.label} link points at ${shortcut.url}`,
      );
    }
  }
});

test("a tool's mark is presented the same way wherever it identifies that tool", () => {
  // It appears in exactly two places: the tool card on the home page and the workflow graphs
  // in the docs. That is what makes it an identity rather than decoration, and what makes two
  // presentations of it a problem.
  //
  // The card wrapped it in a 36px bordered tile and the docs drew it bare. The tile's fill was
  // the page ground, so it was a box of the surrounding colour drawn on the surrounding
  // colour, containing something that needs no containing.
  const read = (file: string) =>
    readFileSync(path.resolve(import.meta.dirname, "..", file), "utf8");
  const home = read("app/page.tsx");
  const docs = read("components/docs/architecture-graph.tsx");

  for (const [name, source] of [["home", home], ["docs", docs]] as const) {
    assert.match(source, /<PdisIcon/, `${name} renders no tool mark`);
  }
  // One size and one tone in both. Layout classes are the call site's business - the card sits
  // the mark beside a title and needs it not to shrink - so this checks what the mark *is*,
  // which is the thing that has to agree, rather than the whole string.
  for (const [name, source] of [["home", home], ["docs", docs]] as const) {
    const marks = [...source.matchAll(/<PdisIcon[^>]*className="([^"]*)"/g)].map((m) => m[1]);
    const heading = marks.filter((value) => value.includes("h-5 w-5"));
    assert.ok(heading.length > 0, `${name} draws no heading-level mark`);
    for (const value of heading) {
      assert.match(value, /\bh-5 w-5\b/, name);
      assert.match(value, /\btext-foreground\b/, name);
    }
  }

  // No tile. A border and a fill around the mark in one place and not the other is the
  // difference this removed.
  const cardHeading = home.slice(
    home.indexOf("function CardHeading"),
    home.indexOf("function CardMeta"),
  );
  assert.ok(
    !/rounded-md border|h-9 w-9/.test(cardHeading),
    "the icon is back inside a tile the other surface does not draw",
  );
});

test("a card's mark, title and arrow are one line", () => {
  // They were two rows: the mark alone with the arrow opposite it, then a 24px gap, then the
  // title. Forty pixels of every card spent putting a 20px glyph on a line of its own, and it
  // left the mark further from the name it identifies than from the arrow it has nothing to do
  // with.
  const home = readFileSync(path.resolve(import.meta.dirname, "..", "app", "page.tsx"), "utf8");

  // One component, so the two card kinds cannot lay this out differently.
  assert.match(home, /function CardHeading\(/);
  assert.ok(!/function CardHeader\(|function CardBody\(/.test(home), "the two rows are back");
  assert.equal((home.match(/<CardHeading/g) ?? []).length, 2, "both card kinds use it");

  const heading = home.slice(home.indexOf("function CardHeading"), home.indexOf("function CardMeta"));
  // The mark and the title are one label, so they share a row and the mark does not shrink.
  assert.match(heading, /<PdisIcon[^>]*shrink-0/);
  assert.match(heading, /<h3[\s\S]{0,200}\{title\}/);
  // The arrow stays on the first line if a title ever wraps.
  assert.match(heading, /items-start/);
});

test("the assistant is entered from the assistant, not from the header", () => {
  // `/ask` renders no content of its own: the page is `WorkspaceAsk` switched to its full-page
  // display. A header link therefore named a destination that does not exist, while the
  // panel's own maximise button says what it does and the panel carries a count of the results
  // it can read.
  const shell = readFileSync(
    path.resolve(import.meta.dirname, "..", "components", "app-shell.tsx"),
    "utf8",
  );
  const code = shell.replace(/\{\/\*[\s\S]*?\*\/\}/g, "");
  assert.ok(!/href="\/ask"/.test(code), "the header links to the assistant again");

  // The route stays, and the panel keeps its way in.
  const panel = readFileSync(
    path.resolve(import.meta.dirname, "..", "components", "assistant", "ask.tsx"),
    "utf8",
  );
  assert.match(panel, /href="\/ask"/, "the maximise button lost its target");
  assert.match(panel, /aria-label="Open full-page assistant"/);

  // Which means the route's only job is a display mode, and it should say so.
  const route = readFileSync(
    path.resolve(import.meta.dirname, "..", "app", "ask", "page.tsx"),
    "utf8",
  );
  assert.match(route, /display mode/, "the empty route does not explain why it is empty");
});

test("a nav label is the word its destination uses", () => {
  // "Docs" is software shorthand, and the docs page's own eyebrow and its section nav both
  // read "Documentation". The link said one word and the destination said another, to a reader
  // who is a product lead rather than a developer. Their own nav abbreviates nothing: About,
  // Our work, Ideas, Media Center, Discovery Center.
  const shell = readFileSync(
    path.resolve(import.meta.dirname, "..", "components", "app-shell.tsx"),
    "utf8",
  );
  const code = shell.replace(/\{\/\*[\s\S]*?\*\/\}/g, "");
  assert.match(code, />Documentation</);
  assert.ok(!/>Docs</.test(code), "the nav label is abbreviated again");

  const page = readFileSync(
    path.resolve(import.meta.dirname, "..", "app", "docs", "page.tsx"),
    "utf8",
  );
  assert.match(page, /Documentation/, "the destination no longer uses the word the link does");
});
