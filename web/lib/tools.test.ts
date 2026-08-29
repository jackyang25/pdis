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

test("a tool states what it does once", () => {
  // Every tool carried a `capability` as well as a description: a two-word label like
  // "Leadership summary" or "Evidence review", which in every case was the description's own
  // words compressed. Three consumers each showed both:
  //
  //   the card    the label under the description it repeated
  //   the docs    joined to it by a middot, inside one sentence
  //   the ask     handed to a model beside the description it repeated
  //
  // With no consumer that needed it, the field went rather than one of its renderings.
  const source = readFileSync(path.resolve(import.meta.dirname, "tools.ts"), "utf8");
  const code = source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
  assert.ok(!/\bcapability\b/.test(code), "a second field for what a tool does is back");

  for (const tool of [...WORKSPACE_TOOLS, ...EXTERNAL_TOOLS]) {
    assert.ok(tool.description.trim().length > 20, `${tool.id} states too little`);
  }
});

test("every judging tool names its territory and its neighbour's", () => {
  // The four differ by the authority they judge against - a rubric, another document,
  // external evidence, a gate's questions - and a reader choosing between them is
  // comparing. Without the boundary clause they infer it from the first half, which is
  // how "does the plan actually work" gets asked of Aligner and "is this complete" of
  // Scout.
  const TERRITORY: Record<string, [string, string]> = {
    inspector: ["Completeness", "correctness"],
    aligner: ["Coherence", "feasibility"],
    scout: ["Feasibility", "completeness"],
    // "Stage gate" is load-bearing, and it is what the process is formally called.
    // `Readiness` alone sits beside `Completeness` - a gate cannot be answered by an
    // incomplete document - so the two read as one question at two scopes. Inspector
    // asks about one document against its template; Screener asks about the whole set
    // against a named decision point in the process.
    screener: ["Stage gate readiness", "judgement"],
  };
  // Checked on the page, not the card. A catalogue of six with six boundary clauses is
  // a second sentence on every card for a distinction that only matters once a reader
  // has chosen one - so the card says what the tool judges, and the page it opens says
  // where that stops.
  for (const [id, [owns, disowns]] of Object.entries(TERRITORY)) {
    assert.ok(
      WORKSPACE_TOOLS.some((entry) => entry.id === id),
      `${id} is no longer catalogued`,
    );
    const page = readFileSync(
      path.resolve(import.meta.dirname, "..", "app", id, "page.tsx"),
      "utf8",
    );
    assert.match(
      page,
      new RegExp(`${owns}, not ${disowns}`),
      `${id}'s page does not say what it owns and what it leaves to another tool`,
    );
  }

  // No two own the same word: that is the whole point of stating them together.
  const owned = Object.values(TERRITORY).map(([owns]) => owns);
  assert.equal(new Set(owned).size, owned.length, "two tools claim one territory");

  // And a disowned word has to point at something. Scout once said "not compliance",
  // which named nothing in the system - compliance with what? - so it disclaimed a
  // territory no reader could go and find. Each disowned word is either another tool's
  // own word, or one of the two things the system deliberately leaves to a person.
  const NOT_OURS = new Set(["judgement", "correctness", "a recommendation"]);
  const claimed = new Set(owned.map((word) => word.toLowerCase().replace("stage gate ", "")));
  for (const [id, [, disowns]] of Object.entries(TERRITORY)) {
    assert.ok(
      claimed.has(disowns) || NOT_OURS.has(disowns),
      `${id} disclaims "${disowns}", which is neither another tool's territory nor `
        + "one of the things no tool does",
    );
  }
});

test("the process is named the way the organisation names it", () => {
  // "Stage gate" is the formal name, and the first time a reader meets the thing is on
  // the card and on the page header. After that "the gate" is ordinary shortening, not
  // drift - you introduce a term once and then use the short form.
  const tool = WORKSPACE_TOOLS.find((entry) => entry.id === "screener")!;
  assert.match(tool.description, /stage gate/, "the card names the process informally");
  // The two places a reader arrives cold, so each introduces the term itself. Checked on
  // the prose a reader sees, not on source order - the file's first "gate" is a variable.
  for (const [file, prop, what] of [
    [["app", "screener", "page.tsx"], "description", "the page header"],
    [["components", "screener-signal-help.tsx"], "intro", "the how-to-read panel"],
  ] as const) {
    const source = readFileSync(path.resolve(import.meta.dirname, "..", ...file), "utf8");
    const [, prose] = source.match(new RegExp(`${prop}="([^"]+)"`)) ?? [];
    assert.ok(prose, `${what} states no ${prop}`);
    assert.match(prose, /stage gate/i, `${what} names the process informally`);
  }
});

test("no card carries a boundary clause", () => {
  // The boundary - which territory a tool owns and which it leaves to a neighbour -
  // lives on the tool's own page, where a reader who has chosen it has room for it. Six
  // of them on a catalogue of six is a second sentence per card for a distinction that
  // only matters once you are about to run one.
  //
  // Archivist is the tempting exception: it is unbuilt, so it has no page, and it is the
  // one tool that judges nothing - a reader can take "past iTPPs required twelve months"
  // as advice to require twelve months. Its limit still waits for its page, because one
  // card carrying a sentence the other five do not is the inconsistency this avoids.
  for (const tool of WORKSPACE_TOOLS) {
    assert.ok(
      !/\b\w+, not \w+/.test(tool.description),
      `${tool.title}'s card carries a boundary clause; that belongs on its page`,
    );
  }
});

test("a tool's page says the same thing its card does", () => {
  // A reader meets the description twice - on the catalogue card and again as the page
  // header - and the two drifted before: the card said "what is missing, off-template,
  // vague" while the page said "every unit the rubric asks about". One tool, two
  // accounts of what it does.
  for (const id of ["inspector", "aligner", "scout", "screener"]) {
    const page = readFileSync(
      path.resolve(import.meta.dirname, "..", "app", id, "page.tsx"),
      "utf8",
    );
    const tool = WORKSPACE_TOOLS.find((entry) => entry.id === id)!;
    // The page may say more; it may not say something different. Its first sentence is
    // the card's first sentence.
    const [opening] = tool.description.split(". ");
    assert.ok(
      page.includes(opening),
      `${id}'s page describes the tool differently from its card`,
    );
  }
});

test("no tool is named for a person, and none for a judgement it does not make", () => {
  // `Expert` failed both. The name promised the thing its own boundary forbids -
  // "Readiness, not judgement" under a word meaning someone whose judgement you trust -
  // and it was the only name that was not an activity:
  //
  //   Inspector  one who inspects
  //   Aligner    one who aligns
  //   Scout      one who scouts
  //   Expert     one who ... knows things
  //
  // It also took the phrase the system needs for the thing no tool does. That collision
  // happened in conversation about the architecture before it happened here.
  const FORBIDDEN = /^(Expert|Reviewer|Auditor|Judge|Adviser|Advisor|Analyst)$/i;
  for (const tool of WORKSPACE_TOOLS) {
    assert.ok(
      !FORBIDDEN.test(tool.title),
      `${tool.title} names a person or a judgement rather than an activity`,
    );
  }
});

test("every reading tool's card is one sentence in one grammar", () => {
  // `<what is read> against|across <the authority>: <what you learn>`
  //
  // Archivist's was the odd one - an imperative and a three-item list, "Look up what
  // past iTPPs and cTPPs required for an attribute, how many said nothing, and the quote
  // behind each value" - so on a page of five it read as a different kind of thing for
  // no reason a reader could name.
  //
  // The preposition carries the one real difference: you hold a document *against* a
  // standard, and you look *across* a corpus. Archivist is the tool that judges nothing,
  // and that shows before the boundary clause on its page ever does.
  const READING = ["inspector", "scout", "aligner", "screener", "archivist"];
  for (const id of READING) {
    const tool = WORKSPACE_TOOLS.find((entry) => entry.id === id);
    assert.ok(tool, `${id} is no longer catalogued`);
    assert.match(
      tool.description,
      / (against|across) .+: /,
      `${tool.title}'s card is not "<what is read> against|across <authority>: <what you learn>"`,
    );
    assert.equal(
      id === "archivist" ? / across /.test(tool.description) : / against /.test(tool.description),
      true,
      id === "archivist"
        ? "Archivist judges nothing, so it looks across a corpus rather than against a standard"
        : `${tool.title} returns a verdict, so it holds something against an authority`,
    );
  }

  // Chunker and Searcher are operations, not readings: they turn a file into blocks or
  // run a query, so they name no authority and their imperative grammar is correct.
  for (const id of ["chunker", "searcher"]) {
    const tool = WORKSPACE_TOOLS.find((entry) => entry.id === id)!;
    assert.ok(
      !/ (against|across) .+: /.test(tool.description),
      `${tool.title} claims an authority; it performs an operation`,
    );
  }
});
