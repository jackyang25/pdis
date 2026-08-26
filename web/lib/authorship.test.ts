/**
 * Who wrote the text on screen, checked across the tools that show model output.
 *
 * `components/ui/evidence-text.tsx` publishes the rule: exact words are ruled and at full
 * contrast, a model's reading is muted prose, computed figures are tabular, and interface
 * copy is muted prose in a box. Full contrast belongs to the tool's own words and the
 * document's values — the only authorship distinction a reader can act on, because it
 * answers "if this is wrong, whose fault is it".
 *
 * Inspector used none of it. Its finding statement and its recommendation are both the
 * model's sentences and rendered at two different contrasts in the same card, which tells
 * a reader they have different authors. Nothing caught it because the rule lived in a
 * component's doc comment and the tools that ignored the component ignored the rule too.
 */

import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";

const REPO = path.resolve(import.meta.dirname, "..");
const read = (...parts: string[]) => readFileSync(path.join(REPO, ...parts), "utf8");

/** The four tools that render a finished result. */
const TOOLS = ["scout", "inspector", "aligner", "expert"] as const;

/** Every `.tsx` under `app/` and `components/`, so a check can ask "anywhere but here". */
function tsxFiles(): string[] {
  const found: string[] = [];
  const walk = (dir: string) => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) walk(full);
      else if (entry.name.endsWith(".tsx")) found.push(full);
    }
  };
  walk(path.join(REPO, "app"));
  walk(path.join(REPO, "components"));
  return found;
}

/** Pages that render sentences a model wrote about a document. */
const MODEL_AUTHORED_PAGES = [
  ["app", "inspector", "page.tsx"],
  ["app", "scout", "page.tsx"],
];

test("a model's sentence is never given full contrast by hand", () => {
  // The specific drift: `<p className="mt-0.5">{finding.statement}</p>`. No tone class
  // means the foreground, which is the tool's own voice.
  const offenders: string[] = [];
  for (const parts of MODEL_AUTHORED_PAGES) {
    const source = read(...parts);
    for (const match of source.matchAll(/<p className="[^"]*">\{[\w.]*\.(statement|reason|recommendation)\}<\/p>/g)) {
      if (!match[0].includes("text-muted-foreground")) {
        offenders.push(`${parts[1]}: ${match[0]}`);
      }
    }
  }
  assert.deepEqual(offenders, [], "a model-authored sentence is rendered at full contrast");
});

test("Inspector reads its model sentences through the shared component", () => {
  // Not merely muted by hand — through `Reading`, so the next sentence added to this card
  // inherits the treatment instead of choosing one.
  const page = read("app", "inspector", "page.tsx");
  assert.match(page, /<Reading size="prominent" className="mt-1 pr-16">/);
});

test("one verdict has one appearance", () => {
  // "Met" rendered as a tinted pill on a unit and as muted text on a section, so the same
  // verdict looked like good news in one row and like an absence in the row above it.
  const page = read("app", "inspector", "page.tsx");
  assert.ok(
    !/return <span className="text-xs text-muted-foreground">Met<\/span>;/.test(page),
    "a section states its verdict in its own words instead of the shared pill",
  );
  assert.match(page, /<StatusPill status="specified" \/>/);
});

test("the quotation rule marks only quotes, in every tool that uses it", () => {
  // `border-l-2` means "these are someone else's exact words". `LabeledItem` also rules its
  // left edge and is deliberately not a quotation — it colours the rule, which is what
  // tells the two apart — so the check is that a bare neutral rule is not applied to a
  // model's prose.
  const labeled = read("components", "labeled-item.tsx");
  assert.match(
    labeled,
    /border-l-\[hsl\(var\(--tone-warning\)\)\]|border-l-foreground/,
    "LabeledItem stopped colouring its rule, so it now looks like a quotation",
  );
});

/**
 * The how-to-read panel, and the labels it explains.
 *
 * Its Finding topic was one eleven-line paragraph defining six reasons in prose, while the
 * same six sat as chips two inches away — two copies of one vocabulary, and the copy a
 * reader has to parse to find the term they are looking at.
 */

test("the panel lists the vocabulary instead of describing it in a paragraph", () => {
  // One list, because there is one axis. It itemised two - reasons and statuses - which
  // is how the panel came to need a paragraph explaining the difference between them.
  const help = readFileSync(path.join(REPO, "components", "inspector-signal-help.tsx"), "utf8");
  assert.match(help, /terms: VERDICTS\.map/, "the verdicts are not itemised");
});

test("the panel reads the labels rather than restating them", () => {
  // A retyped list is a second copy that drifts. Built from the maps, the panel cannot
  // come to explain a word the interface no longer uses.
  const help = readFileSync(path.join(REPO, "components", "inspector-signal-help.tsx"), "utf8");
  assert.match(help, /term: VERDICT_LABEL\[verdict\]/);
  assert.match(help, /meaning: VERDICT_DESCRIPTION\[verdict\]/);
});

test("every verdict has a short label and a full description", () => {
  // A verdict renders as an inline chip, as a pill, and as the options of the trace's
  // layer selector, where a five-word sentence wrapped onto two lines.
  const api = readFileSync(path.join(REPO, "lib", "api.ts"), "utf8");
  const labels = api.match(/export const VERDICT_LABEL:[\s\S]*?\n\};/)?.[0] ?? "";
  const descriptions = api.match(/export const VERDICT_DESCRIPTION:[\s\S]*?\n\};/)?.[0] ?? "";
  assert.ok(descriptions, "verdicts have no description map");
  const keys = (block: string) => (block.match(/^\s{2}(\w+):/gm) ?? []).map((k) => k.trim());
  assert.deepEqual(keys(labels), keys(descriptions), "the two maps cover different verdicts");
});

test("a label stays short enough to sit in a chip", () => {
  // What went wrong: these were written as explanations, so they ran to five words and the
  // document trace rendered one as inline pill text.
  const api = readFileSync(path.join(REPO, "lib", "api.ts"), "utf8");
  const block = api.match(/export const REASON_LABELS[\s\S]*?\n\};/)?.[0] ?? "";
  for (const [, label] of block.matchAll(/^\s{2}\w+: "([^"]+)",$/gm)) {
    assert.ok(
      label.split(" ").length <= 2,
      `"${label}" is an explanation, not a label; put it in REASON_DESCRIPTION`,
    );
  }
});

/**
 * Shared where the job is shared, bespoke where the data differs.
 *
 * "How many of each verdict" is one idea and four tools built it four ways: dot chips,
 * tinted pills, plain muted text, labelled cells. None was wrong on its own, which is what
 * let it survive - the cost lands on a reader moving between tools, who learns one idea
 * four times.
 */

test("no tool hand-rolls its own row of verdict counts", () => {
  const offenders: string[] = [];
  for (const tool of ["inspector", "aligner"]) {
    const page = readFileSync(path.join(REPO, "app", tool, "page.tsx"), "utf8");
    if (!page.includes("VerdictCounts")) offenders.push(tool);
  }
  assert.deepEqual(offenders, [], "a tool counts verdicts in its own shape");
});

test("a count row uses dots, never tints", () => {
  // The rule in `lib/tone.ts`: several signals share this row and none is dominant, so a
  // tint on each turns it into a bar chart of colour while the reader is comparing counts.
  const counts = readFileSync(path.join(REPO, "components", "ui", "verdict-counts.tsx"), "utf8");
  assert.match(counts, /SignalChip/);
  assert.ok(!counts.includes("TONE_TINT"), "the count row fills its chips");
});

test("the tone scale says which shape a situation calls for", () => {
  // It listed three shapes and where each goes, and never which situation gets which -
  // so four tools each picked one. The list without the rule is what allowed the drift.
  const tone = readFileSync(path.join(REPO, "lib", "tone.ts"), "utf8");
  assert.match(tone, /Which shape, and when/);
  assert.match(tone, /several signals in one row/i);
});

test("one verdict has one tone, wherever it is drawn", () => {
  // Aligner decided its verdict tones twice: once for the count row and once for the
  // document trace, in two vocabularies that call the same reading `warning` and
  // `caution`. One map now, with the trace translating.
  const api = readFileSync(path.join(REPO, "lib", "api.ts"), "utf8");
  assert.match(api, /export const ALIGNMENT_VERDICT_TONE/);
  const trace = readFileSync(path.join(REPO, "lib", "aligner-document-trace.ts"), "utf8");
  assert.ok(
    !/falls_short: "caution"/.test(trace),
    "the aligner trace holds its own copy of the verdict tones again",
  );
});

test("no tool keeps its own copy of the shared chip", () => {
  // Scout owned `SignalChip` while three tools reinvented the same row. Promoting it left
  // Scout with a duplicate for one round, which is the smell the promotion was removing.
  for (const tool of TOOLS) {
    const page = readFileSync(path.join(REPO, "app", tool, "page.tsx"), "utf8");
    assert.ok(
      !/^function SignalChip\(/m.test(page),
      `${tool} defines its own SignalChip beside the shared one`,
    );
  }
});

test("a verdict chip is given a tone, never a class name", () => {
  // Why this is worth more than a dedupe. The local version took `dot: string`, so any
  // caller could hand it a raw palette class — which is how eighteen of them reached Scout
  // with no dark-mode variant, per the note in `lib/tone.ts`. The shared one takes a
  // `Tone`, which makes that unrepresentable rather than merely discouraged.
  const chip = readFileSync(path.join(REPO, "components", "ui", "signal-chip.tsx"), "utf8");
  assert.match(chip, /tone: Tone;/);
  assert.ok(!/dot: string/.test(chip), "the shared chip accepts a class name again");
  const scout = readFileSync(path.join(REPO, "app", "scout", "page.tsx"), "utf8");
  assert.ok(
    !/dot\?: string;/.test(scout),
    "a Scout component takes a raw dot class instead of a tone",
  );
});

test("a popover can never grow taller than the screen", () => {
  // A portalled panel that overruns the viewport cannot be scrolled to: the page behind
  // it does not move, so the rest of the content is simply unreachable. The how-to-read
  // panel crossed that line the moment its vocabulary was itemised into a list.
  //
  // Capped in the primitive rather than at each panel, because no popover should be able
  // to do this and three had already hand-rolled their own max-height.
  const popover = readFileSync(path.join(REPO, "components", "ui", "popover.tsx"), "utf8");
  assert.match(popover, /max-h-\[var\(--radix-popover-content-available-height\)\]/);
  assert.match(popover, /overflow-y-auto/);
});

/**
 * One fact, rendered once.
 *
 * A variable the document never wrote has both its sentences templated in
 * `services/inspector/assembly.py` out of three fields already on the row - the unit name,
 * its section, and its reason. On a six-variable absent section that was one fact rendered
 * twenty-five times, and the template text was shown through `Reading`, the treatment that
 * means a model judged it.
 */

test("a unit is not described twice in two sentences", () => {
  // There used to be a `recommendation` beside every statement, restating it as an
  // imperative: "Target User Group is not present" and "Add the section and state Target
  // User Group", built from the same three fields already on the row. The page had grown
  // a `restatesItself()` guard to hide one of them on the one case where both were pure
  // template. Removing the field removed the need for the guard - and the guard's own
  // narrowness, which only covered variables and not sections.
  // Checked on code rather than on the whole file: both the page and this test explain
  // in prose what they no longer do, and a comment naming the guard is not the guard.
  const page = readFileSync(path.join(REPO, "app", "inspector", "page.tsx"), "utf8");
  assert.ok(
    !/function restatesItself/.test(page),
    "the restatement guard is back, so the field is too",
  );
  assert.ok(
    !/\{finding\.recommendation\}/.test(page),
    "a second sentence renders beside the statement",
  );
  const api = readFileSync(path.join(REPO, "lib", "api.ts"), "utf8");
  const assessment = api.slice(api.indexOf("export type Assessment = {"));
  assert.ok(
    !/recommendation/.test(assessment.slice(0, assessment.indexOf("};"))),
    "the published atom carries a recommendation again",
  );
});

test("an absent section still says what it should have covered", () => {
  // The rubric's description of what the section should contain appears nowhere else on
  // screen, so it survived the removal of the field it used to live in. A `recommendation`
  // carried it, and that field restated the statement in every other case - "Target User
  // Group is not present" beside "Add the section and state Target User Group" - which is
  // why the web layer had grown a guard to hide one of the two. The field went; this fact
  // moved into the sentence rather than going with it.
  const assembly = readFileSync(
    path.join(REPO, "..", "services", "inspector", "assembly.py"),
    "utf8",
  );
  assert.match(assembly, /It should cover: \{spec\.description\}/);
  assert.ok(
    !/recommendation=/.test(assembly),
    "the recommendation field is back, so one fact has two sentences again",
  );
});

test("a verdict has one tone, and the pill and the count row both read it", () => {
  // Two maps would be one verdict decided twice, which is how a verdict comes to be one
  // colour on a unit and another on the section summarising it.
  const page = readFileSync(path.join(REPO, "app", "inspector", "page.tsx"), "utf8");
  assert.match(page, /const VERDICT_TONE: Record<Verdict, Tone>/);
  assert.match(
    page,
    /VERDICT_SURFACE[\s\S]{0,140}TONE_TINT\[VERDICT_TONE\[verdict\]\]/,
    "the tint map decides its own colours again instead of reading the tone",
  );
});

test("a section's counts are counts of units, in the units' own words", () => {
  // They were typed `Record<FindingLevel, number>` and labelled with the finding
  // vocabulary while counting units, so "Not met 10" on a section and "Not met" on a unit
  // used one word for two denominators. There is one vocabulary now, so the section row
  // and the unit pill read the same map and the mismatch is not expressible.
  const api = readFileSync(path.join(REPO, "lib", "api.ts"), "utf8");
  assert.match(api, /verdict_counts: Record<Verdict, number>/);
  const page = readFileSync(path.join(REPO, "app", "inspector", "page.tsx"), "utf8");
  assert.match(page, /label: VERDICT_LABEL\[verdict\]/, "the section row invents its own words");
  assert.match(page, /VERDICT_LABEL\[status\]/, "the unit pill invents its own words");
});

/**
 * Four zones, and what belongs in each.
 *
 *   header    who the result is about, and what you can do with the whole run
 *   tab row   navigation, and nothing else
 *   toolbar   what filters, searches, counts or explains the content below it
 *   content   the result, including any summary derived from it
 *
 * Every tool had a toolbar and every tool placed it differently. Scout wrote the band twice
 * and put "How to read" in it on one tab; Inspector put "How to read" on the tab row, where
 * it reads as an affordance on the tabs rather than on anything they contain; and Scout's
 * Fields toolbar sat below a coverage line and a priorities panel, so the chrome was inside
 * the content it controls.
 */

test("no tool hand-rolls the toolbar band", () => {
  // Matched on the toolbar's own shape - a column that becomes a centred row - rather than
  // on the tint alone. Scout's unresolved-field notice shares the tint deliberately and is
  // not a toolbar; a looser pattern flagged it and would have pushed a notice into a
  // component for controls.
  const band = /flex flex-col gap-2 border-b border-border\/60 bg-foreground\/\[0\.045\]/;
  for (const tool of TOOLS) {
    const page = readFileSync(path.join(REPO, "app", tool, "page.tsx"), "utf8");
    assert.ok(!band.test(page), `${tool} writes the toolbar band by hand`);
  }
});

test("every tool builds its result through the shared layout", () => {
  // The zones were an arrangement each tool remembered, and each drifted somewhere: Scout's
  // run-wide coverage sat inside its Fields tab, Inspector's priorities inside Sections,
  // one tab row drew a heavier rule than the boundaries around it, and "How to read" sat on
  // a tab row where it explained navigation rather than results.
  //
  // Now the zones are arguments. This replaces two tests that asserted their order, because
  // a component that makes wrong order unexpressible is stronger than a test reporting it.
  for (const tool of TOOLS) {
    const page = readFileSync(path.join(REPO, "app", tool, "page.tsx"), "utf8");
    assert.match(page, /<ResultLayout/, `${tool} assembles its own result layout`);
    assert.ok(
      !/<TabsList/.test(page),
      `${tool} builds its own tab row instead of passing triggers to the layout`,
    );
  }
});

test("the layout keeps the header one block and every boundary one weight", () => {
  const layout = readFileSync(
    path.join(REPO, "components", "ui", "result-layout.tsx"),
    "utf8",
  );
  // The figures are behind `ResultMetrics` in the header's trailing row and the card's own
  // rule is off, so the header is one block - name, scope, actions, tabs - ending at one
  // edge: the tab row's. As a line of its own the figures overlapped the subtitle above
  // them, two sentences of numbers sharing a count before a single result.
  assert.match(layout, /<ResultMetrics[\s\S]*?\{metrics\}/, "the figures are a header line again");
  assert.match(layout, /separated=\{false\}/, "the card rules the header off from the tabs");
  const header = layout.slice(layout.indexOf("<Tabs "), layout.indexOf("{priorities &&"));
  // `border-b-0` removes a rule rather than drawing one, so it is not counted: the tab
  // list clears the underline its own component ships with.
  assert.equal(
    (header.match(/border-b border-/g) ?? []).length,
    1,
    "the header draws more than the one rule that ends it",
  );
  assert.ok(
    !/border-b border-border\b(?!\/)/.test(layout),
    "a boundary is drawn at a heavier weight than the others",
  );
});



test("a view says what opening it gives you, once", () => {
  // The count moved to the toolbar, where the nav states it beside the search. What is left
  // is the one thing the rows cannot say for themselves: that a section holds every unit
  // the rubric asks about, not only the ones that produced a finding.
  const page = readFileSync(path.join(REPO, "app", "inspector", "page.tsx"), "utf8");
  assert.ok(
    !page.includes("Each row carries its own counts"),
    "the description still describes the interface instead of the content",
  );
  assert.match(page, /Open a section to see every unit the rubric asks about/);
  assert.equal(
    (page.match(/Open a section to see every unit/g) ?? []).length,
    1,
    "the sentence is stated twice",
  );
});

/**
 * A result names itself the same way everywhere.
 *
 * The card title held four different kinds of thing: Inspector the document, Scout a count
 * of the rubric, Aligner the tool's own noun, Expert the gate — which its subtitle then
 * repeated. Scout never named the document it analysed at all, which is the one fact that
 * tells a reader which run they are looking at.
 *
 * `runLabel` already answered this for the run picker and the download filename, so a run
 * had one name in two places and something else in the third.
 */

test("every result card is titled by the run's own identity", () => {
  for (const tool of TOOLS) {
    const page = readFileSync(path.join(REPO, "app", tool, "page.tsx"), "utf8");
    assert.match(
      page,
      new RegExp(`title=\\{runLabel\\(result, "${tool}"\\)\\}`),
      `${tool} titles its result card with something of its own`,
    );
  }
});

test("a page description says what the tool answers, not how it works", () => {
  // Five tools described a question and two described a mechanism, in internal vocabulary:
  // "through one normalized workspace", "for downstream intelligence workflows".
  const mechanical = /Transform source documents|normalized workspace|downstream intelligence/;
  for (const tool of ["scout", "inspector", "aligner", "expert", "archivist", "searcher", "chunker"]) {
    const page = readFileSync(path.join(REPO, "app", tool, "page.tsx"), "utf8");
    assert.ok(!mechanical.test(page), `${tool} describes its mechanism rather than its question`);
  }
});

test("the priorities panel starts closed, like everything around it", () => {
  // It was the one disclosure on the page that opened by default, so a reader who had read
  // it once closed it again on every run.
  const panel = readFileSync(path.join(REPO, "components", "ui", "priority-panel.tsx"), "utf8");
  assert.match(panel, /defaultOpen = false/);
});

test("a toolbar is never only its right-hand end", () => {
  // Inspector's toolbars held nothing but "How to read" and a count, so the band read as an
  // empty strip. The left side takes a control where there is something to filter and the
  // view's name where there is not - three conflicts do not need a search.
  //
  // Across all four now, not just Inspector: the band is shared, so the rule about what
  // may be in it is one rule. `<ResultSearch` rather than `type="search"`, because the
  // input moved into its own component and every toolbar reaches it by that name.
  let checked = 0;
  for (const tool of TOOLS) {
    const page = readFileSync(path.join(REPO, "app", tool, "page.tsx"), "utf8");
    for (const band of page.split("<ResultToolbar>").slice(1)) {
      const inner = band.slice(0, band.indexOf("</ResultToolbar>"));
      const end = inner.indexOf("<ResultToolbarEnd>");
      const left = end === -1 ? inner : inner.slice(0, end);
      assert.ok(
        /<ResultSearch/.test(left) || /<p /.test(left),
        `${tool} has a toolbar with nothing on its left: ${inner.slice(0, 80)}`,
      );
      checked += 1;
    }
  }
  assert.ok(checked >= 5, `only ${checked} toolbars found; a tool lost its band`);
});

/**
 * Three zones should read as three, not as eight strips.
 *
 * A rule is a boundary. Once the coverage line, the tab row, the priorities panel and the
 * toolbar each drew one, the header alone looked like three stacked components — and a
 * reader counting boxes counts wrong about what belongs to what.
 */

test("a zone boundary is one rule, at one weight", () => {
  // `border-border` at full opacity read heavier than the `/60` every other boundary uses,
  // so the tab row looked like the end of something rather than part of the header.
  for (const tool of ["scout", "inspector"]) {
    const page = readFileSync(path.join(REPO, "app", tool, "page.tsx"), "utf8");
    const tabs = page.slice(page.indexOf("<Tabs "), page.indexOf("<TabsList"));
    assert.ok(
      !/border-b border-border\b(?!\/)/.test(tabs),
      `${tool}'s tab row draws a heavier rule than the zones around it`,
    );
  }
});

test("the header draws no rule inside itself", () => {
  // Identity, figures and navigation are one block. The coverage line used to end with a
  // border, which split the run's name from the run's numbers.
  const page = readFileSync(path.join(REPO, "app", "scout", "page.tsx"), "utf8");
  const coverage = page.slice(page.indexOf("function RunCoverage"));
  const opening = coverage.slice(0, coverage.indexOf(">"));
  assert.ok(
    !opening.includes("border-b"),
    "the coverage line rules itself off from the title above it",
  );
});


test("the search box is one component, not a class string four tools copied", () => {
  // It was copied, character for character, three times. Identical is how a copy starts;
  // one of them drifting to a different height or focus ring is how it ends, with nobody
  // able to say which was right. The check is on the input rather than on the class,
  // because a tool that writes its own `<input type="search">` has already left.
  const owner = path.join("components", "ui", "result-search.tsx");
  for (const file of tsxFiles()) {
    if (file.endsWith(owner)) continue;
    const source = readFileSync(file, "utf8");
    assert.ok(
      !/type="search"/.test(source),
      `${path.relative(REPO, file)} builds its own search input instead of using ResultSearch`,
    );
  }
});

test("a toolbar ends the shared way, and insets the header figures nowhere but the layout", () => {
  // One of five toolbars pushed its count right with its own `sm:ml-auto` instead of
  // `ResultToolbarEnd`, so a change to how a toolbar ends would have reached four of them.
  for (const tool of TOOLS) {
    const page = readFileSync(path.join(REPO, "app", tool, "page.tsx"), "utf8");
    for (const toolbar of page.match(/<ResultToolbar>[\s\S]*?<\/ResultToolbar>/g) ?? []) {
      assert.ok(
        !/ml-auto/.test(toolbar) || /<ResultToolbarEnd[\s>]/.test(toolbar),
        `${tool} aligns a toolbar's right-hand end by hand instead of using ResultToolbarEnd`,
      );
    }
    // The figure row is passed bare and the layout insets it. Two tools passed a bare row
    // and one padded its own, so the same zone was aligned two ways across the four.
    const metrics = page.slice(page.indexOf("metrics={"), page.indexOf("tabValue="));
    assert.ok(
      !/\bpx-5\b/.test(metrics),
      `${tool} insets its own header figures; the inset belongs to CollapsibleCard's header`,
    );
  }
});

test("the priorities panel shows on the tab its items link into", () => {
  // It sat above every tab, because it is selected from the whole result. But every item
  // is a link into one tab, so on Scout's Documents view it nominated fields that were
  // not on screen, and on the Evidence map it was a closed grey band above the thing you
  // came for. Selected-from and shown-on are different questions.
  const layout = read("components", "ui", "result-layout.tsx");
  assert.match(
    layout,
    /priorities\.tab === tabValue/,
    "the priorities panel renders on every tab again",
  );
  for (const tool of TOOLS) {
    const page = read("app", tool, "page.tsx");
    if (!page.includes("priorities={")) continue;
    const slot = page.slice(page.indexOf("priorities={"), page.indexOf("priorities={") + 400);
    const tab = slot.match(/tab: "([a-z]+)"/);
    assert.ok(tab, `${tool} supplies a priorities panel without saying which tab it links into`);
    assert.ok(
      page.includes(`<TabsTrigger value="${tab[1]}">`),
      `${tool} points its priorities at "${tab[1]}", which is not one of its tabs`,
    );
  }
});

test("a count that equals its total is not shown", () => {
  // "36 of 36" is the filter reporting that it is not filtering, beside a subtitle that
  // already said 36. The decision is made once in `ResultToolbarEnd` rather than at five
  // call sites, so no tool has to remember to stay quiet.
  const toolbar = read("components", "ui", "result-toolbar.tsx");
  assert.match(
    toolbar,
    /count\.shown !== count\.total/,
    "the toolbar shows a count even when nothing is filtered",
  );
  for (const tool of TOOLS) {
    const page = read("app", tool, "page.tsx");
    for (const band of page.match(/<ResultToolbarEnd[\s\S]*?<\/ResultToolbarEnd>/g) ?? []) {
      assert.ok(
        !/\{\s*\w[\w.]*\.length\s*\}\s*of\s*\{/.test(band),
        `${tool} writes its own "n of m" instead of passing count to ResultToolbarEnd`,
      );
    }
  }
});

test("the explainer is the last thing on a toolbar", () => {
  // It is the one item whose width never changes, so it holds the right edge still.
  // With the count outside it, filtering from "36 of 36" to "4 of 36" shifted the band.
  const toolbar = read("components", "ui", "result-toolbar.tsx");
  const end = toolbar.slice(toolbar.indexOf("export function ResultToolbarEnd"));
  assert.ok(
    end.indexOf("{count") < end.indexOf("{children}"),
    "the count renders after the explainer, so the right edge moves as you filter",
  );
});

test("the run's figures are stated once, not twice in two grammars", () => {
  // The subtitle said "36 fields · 1,491 insights in these fields" and the row under it
  // said "31 of 36 fields stated a target". Two sentences of numbers before a single
  // result, sharing a 36 the reader had to work out was the same 36. The subtitle keeps
  // scope - what was examined - and every outcome figure lives behind `ResultMetrics`.
  const layout = read("components", "ui", "result-layout.tsx");
  assert.match(layout, /<ResultMetrics/, "the figures are not behind the metrics panel");
  for (const tool of TOOLS) {
    const page = read("app", tool, "page.tsx");
    const call = page.slice(page.indexOf("<ResultLayout"), page.indexOf("tabValue="));
    const subtitle = call.slice(call.indexOf("subtitle="), call.indexOf("metrics="));
    // Scope reads as a count of what was examined. An outcome verb in the subtitle means
    // the header is reporting results again.
    assert.ok(
      !/\b(stated|grounded|met|answered|found|flagged)\b/.test(subtitle),
      `${tool} reports an outcome in its subtitle; the subtitle is scope`,
    );
  }
});

test("the priorities band is flush with the bands around it", () => {
  // Tab row, priorities, toolbar - three consecutive zones. The middle one was an inset
  // bordered card between two full-bleed bands, so it read as a component sitting inside
  // the result rather than as one of its zones, and it was the only one whose left edge
  // did not line up with the title.
  const panel = read("components", "ui", "priority-panel.tsx");
  assert.ok(
    !/<section className="[^"]*\bborder border-border\b/.test(panel),
    "the priorities panel draws its own card border inside the layout",
  );
  const layout = read("components", "ui", "result-layout.tsx");
  const band = layout.slice(layout.indexOf("{priorities &&"));
  assert.ok(
    !/px-5/.test(band.slice(0, band.indexOf("</div>"))),
    "the layout insets the priorities band, so it no longer lines up with the tab row",
  );
});

test("the caption under a run's name is the configuration, in one grammar", () => {
  // Four tools, four sentences, each derived from that tool's own output: Scout counted
  // fields, Inspector sections and units, Aligner comparisons. The counts restated figures
  // the metrics panel already holds, they were phrased in whatever unit that tool happens
  // to use, and "36 fields" described the Fields tab rather than the run - on Documents it
  // named something not on screen.
  //
  // Now it is what the reader typed into the header form: indication, intervention class,
  // document type. Predictable before the run finishes, and identical across the four.
  for (const tool of TOOLS) {
    const page = read("app", tool, "page.tsx");
    const call = page.slice(page.indexOf("<ResultLayout"), page.indexOf("tabValue="));
    const subtitle = call.match(/subtitle=\{([^}]*)\}/);
    assert.ok(subtitle, `${tool} states no caption under its run's name`);
    assert.equal(
      subtitle[1].trim(),
      `runScope(result, "${tool}")`,
      `${tool} builds its own caption instead of naming the run's configuration`,
    );
  }
});

test("the priorities panel is bounded, and says when it is", () => {
  // Inspector returned its entire worklist - eighteen findings on a normal run, four lines
  // each with a source trigger - so opening the panel pushed every result off the screen
  // it was supposed to introduce. Scout capped at eight and the other three did not.
  //
  // A cap rather than a scrolling box: the panel opens closed, so a scrollbar inside
  // something you just opened hides what you asked for, and a nested scroll region
  // captures the wheel on the way past. Nothing is lost - every order note already says
  // each item also appears in the list below.
  const panel = read("components", "ui", "priority-panel.tsx");
  assert.match(
    panel,
    /items\.slice\(0, PRIORITY_LIMIT\)/,
    "the priorities panel renders every item its tool raised",
  );
  assert.ok(
    !/overflow-y-auto|max-h-/.test(panel),
    "the priorities panel scrolls inside itself instead of stopping at the limit",
  );
  // Bounded by default, not truncated. These are a worklist - every one of Inspector's is
  // a rubric unit somebody has to fix - so the ones past eight are jobs, and a sentence
  // pointing at the tab below asks a reader to find rows they cannot identify. The reader
  // decides how many is enough; the default decides what the panel costs on arrival.
  assert.match(
    panel,
    /items\.length > PRIORITY_LIMIT/,
    "the panel truncates silently, so a partial list reads as the whole one",
  );
  assert.match(
    panel,
    /setShowAll/,
    "the panel drops items with no way to see them",
  );
  assert.match(
    panel,
    /aria-expanded=\{showAll\}/,
    "the show-all control does not say whether it is expanded",
  );
  // One number. Scout's selector stops at the limit rather than truncating after it, and
  // the two must not be able to disagree about where that is.
  const scout = read("lib", "scout-priorities.ts");
  assert.match(
    scout,
    /SCOUT_PRIORITY_LIMIT = PRIORITY_LIMIT/,
    "Scout keeps its own copy of the priority limit",
  );
});

test("units in one list are one row each, at one left edge", () => {
  // A unit used to open: a chevron on the row, the sentence behind it. That was right
  // when a unit held several findings - a thirteen-unit section was sixty lines - and
  // wrong once a unit held one verdict and one sentence of at most twenty words, which
  // put two lines behind a click and asked a reader to make thirty-two of them.
  //
  // It also removes the bug that made the row alignment matter: a unit with nothing to
  // disclose had no chevron and so no indent, which read as a heading over the rows
  // below it. With no chevron anywhere, there is no edge to get wrong.
  const page = read("app", "inspector", "page.tsx");
  assert.ok(
    !/<details/.test(page),
    "a unit opens again, so the assessment costs one click per unit to read",
  );
  assert.ok(
    !/ChevronDown/.test(page),
    "a row carries a chevron, so rows with and without one sit at different edges",
  );
  // One renderer for one shape: a rubric unit and a cross-section conflict are the same
  // thing now, and rendering them two ways is two things to keep in step.
  assert.match(page, /function AssessmentRow\(/, "the shared row is gone");
  assert.ok(
    !/function (FindingBody|UnitRow)\(/.test(page),
    "a second renderer for the same shape is back",
  );
});

test("the authorship mark is rendered once, by the component", () => {
  // The whole point of the mark living in `Reading`: adding it per sentence would put
  // it on the sentences somebody remembered and nowhere else, and coverage is the
  // thing it is for. One render site, twenty-odd call sites, every instance marked.
  const text = read("components", "ui", "evidence-text.tsx");
  assert.match(text, /function ReadingMark\(/, "the mark is no longer a component");
  assert.equal(
    (text.match(/<ReadingMark \/>/g) ?? []).length,
    1,
    "the mark is rendered more than once, so a call site can render it by hand",
  );
  const marks = tsxFiles()
    .filter((file) => !file.endsWith(path.join("ui", "evidence-text.tsx")))
    .filter((file) => /ReadingMark/.test(readFileSync(file, "utf8")));
  assert.deepEqual(marks, [], "a call site reaches for the mark instead of Reading");
});

test("a model's sentence reaches the page through Reading, never as bare prose", () => {
  // The coverage rule. A sentence rendered as a hand-written `<p>` gets no mark, no
  // tone and no size from the system - and there were eight of them, four of which had
  // independently agreed on `text-sm leading-6 text-foreground/85`, a third tone that
  // is neither a model's muted prose nor the tool's full contrast. Agreement between
  // four hand-written copies is what made it look deliberate.
  //
  // The fields listed are the ones a model authors. A new one is not covered until it
  // is added here, which is the honest limit of a source check.
  // `summary` is qualified by its object: a trace annotation's is a model's sentence,
  // while `topic.summary` in the help panel and `data.summary` in the docs diagram are
  // the tool explaining itself. Naming the field alone caught all three.
  const AUTHORED = /\{(?:\w+\.(?:statement|recommendation|missing)|(?:annotation|ref)\.summary)\}/;
  const offenders: string[] = [];
  for (const file of tsxFiles()) {
    const source = readFileSync(file, "utf8");
    for (const [line] of source.split("\n").entries()) void line;
    const lines = source.split("\n");
    lines.forEach((text, index) => {
      if (!AUTHORED.test(text)) return;
      // Look at the element this sits in: the same line, or the one above it when the
      // value is on a line of its own.
      const element = /^\s*\{/.test(text) ? `${lines[index - 1] ?? ""}${text}` : text;
      if (!/<p[\s>]/.test(element)) return;
      offenders.push(`${path.relative(REPO, file)}:${index + 1}`);
    });
  }
  assert.deepEqual(
    offenders,
    [],
    "a model-authored sentence is rendered as a bare paragraph instead of <Reading>",
  );
});
