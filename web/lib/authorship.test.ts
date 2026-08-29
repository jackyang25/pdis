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
const TOOLS = ["scout", "inspector", "aligner", "screener"] as const;

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
  // The tint is applied by `VerdictPill`, which reads the tone directly. A verdict-to-class
  // map lived on the page as well, which is one lookup more than the fact needs.
  const pill = read("components", "ui", "verdict-pill.tsx");
  assert.match(pill, /TONE_TINT\[tone\]/, "the pill decides its own colours again");
  assert.ok(
    !/VERDICT_SURFACE/.test(page),
    "the page keeps a second map from verdict to class",
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
 * of the rubric, Aligner the tool's own noun, Screener the gate — which its subtitle then
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
  for (const tool of ["scout", "inspector", "aligner", "screener", "archivist", "searcher", "chunker"]) {
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
  //
  // The path is `[\w.]+`, not `\w+`. Written to match one segment it missed
  // `match.insight.statement` twice in Scout - one of them rendered at full contrast,
  // the treatment reserved for the tool's own words - because nothing said the check
  // only covered fields exactly one dot deep.
  const AUTHORED =
    /\{(?:[\w.]+\.(?:statement|recommendation|missing)|(?:annotation|ref)\.summary)\}/;
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

test("the mark belongs to a contribution, not to every sentence in it", () => {
  // Two stars stacked read as a list of equals. An insight and the model's note about
  // that insight are one contribution - same author, one level apart - so the first
  // carries the mark and the second is indented under it.
  //
  // The hierarchy used to come from contrast: the insight at full, the note muted. That
  // looked right and said the wrong thing, because contrast is the authorship axis and
  // both lines have one author. Indentation carries level, the mark carries authorship.
  const text = read("components", "ui", "evidence-text.tsx");
  assert.match(text, /\{!continued && <ReadingMark \/>\}/, "a continuation is marked again");
  assert.match(text, /continued && "pl-\[/, "a continuation is no longer indented under its line");

  // Not a source scan for adjacent `Reading`s: two of them in a file are as likely to be
  // mutually exclusive branches - a skipped search and a failed one - as a stacked pair,
  // and a check that flags correct code only teaches people to work around it. What is
  // checkable is that the mechanism exists and that the pairs which do stack use it.
  for (const [file, first, second] of [
    [["app", "scout", "page.tsx"], "match.insight.statement", "match.reason"],
    [["app", "screener", "page.tsx"], "question.statement", "question.missing"],
    [["components", "ui", "priority-panel.tsx"], "item.statement", "item.recommendation"],
  ] as const) {
    const source = read(...file);
    // The render site, not the first mention: the comment above one of these names the
    // field in prose, and matching that put the window on the explanation rather than on
    // the element. `{` is what tells an interpolation from a mention.
    const at = source.indexOf(`{${second}`);
    assert.ok(at > 0, `${second} is no longer rendered here`);
    assert.ok(source.indexOf(`{${first}`) > 0, `${first} is no longer rendered here`);
    const note = source.slice(at, at + 200);
    assert.match(
      note,
      /continued/,
      `${second} is marked in its own right, so it reads as a second contribution`,
    );
  }
});

test("the tool's voice is boxed only when it is an aside", () => {
  // The box says "read this differently from what surrounds it". That is right for a
  // caveat beside data, a warning above it, or a summary under it - and wrong when the
  // sentence *is* what the section contains, because then there is nothing to be set off
  // from. A field with no measurable targets answers with a sentence saying why, and
  // boxing it made an absence the only bordered element on a card of flat prose: the
  // loudest thing on screen, for the least information.
  const text = read("components", "ui", "evidence-text.tsx");
  assert.match(
    text,
    /variant === "note" && "rounded-md border/,
    "the box is drawn for every interface sentence again, aside or not",
  );
  // The box still earns its place on an aside, and this is why: the mark created a
  // second kind of unstarred muted prose - a `continued` note under a model's sentence.
  // Without the box, the tool's own voice and a model's continuation would be told apart
  // by position alone, which is the rule a reader has to have been told.
  assert.match(text, /variant = "note"/, "an interface sentence defaults to unboxed");
});

test("a pill's shape says which question it answers", () => {
  // Three roles, three shapes, one owner each - so a shape never has to be read in
  // context to know what it means:
  //
  //   verdict   how this thing stands, judged.   tinted, rounded-md   VerdictPill
  //   category  what kind of thing it is.        outlined, rounded-full  Badge
  //   count     how many of each verdict.        a dot and a number   SignalChip
  //
  // The verdict shape had drifted into three. Inspector's list drew the tinted pill while
  // the Scout and Inspector trace panels each hand-wrote the same neutral outlined one -
  // character for character identical across two files, for a value that is never
  // neutral, and both had the tone on the annotation and discarded it.
  const pill = read("components", "ui", "verdict-pill.tsx");
  assert.match(pill, /rounded-md/, "a verdict is no longer tinted and square-cornered");
  const badge = read("components", "ui", "badge.tsx");
  assert.match(badge, /rounded-full/, "a category is no longer outlined and round");

  // Nobody draws the old neutral trace pill by hand any more.
  for (const file of tsxFiles()) {
    const source = readFileSync(file, "utf8");
    assert.ok(
      !/rounded-full border border-border\/80 bg-foreground\/\[0\.045\]/.test(source),
      `${path.relative(REPO, file)} hand-draws a verdict pill instead of using VerdictPill`,
    );
  }
});

test("there is one tone vocabulary, not one per layer", () => {
  // The trace layer declared its own four and called the middle one `caution` while
  // `lib/tone.ts` called it `warning`. One thing, two names - and `aligner-document-trace`
  // carried a line whose entire job was translating between them.
  const trace = read("lib", "document-trace.ts");
  assert.match(trace, /tone: Tone;/, "the trace declares its own tone list again");
  for (const file of [...tsxFiles(), ...["document-trace", "inspector-document-trace",
    "aligner-document-trace", "screener-document-trace"].map((name) =>
    path.join(REPO, "lib", `${name}.ts`))]) {
    const source = readFileSync(file, "utf8");
    assert.ok(
      !/tone: "caution"/.test(source),
      `${path.relative(REPO, file)} uses a second name for the warning tone`,
    );
  }
});

test("a trace summary is marked by who wrote it, not by which panel shows it", () => {
  // Scout's six annotation kinds draw their summary from six places, and two of them -
  // a field's stated target and the passage a measurable target was read from - are the
  // document's own words. Rendering every summary as a model's put the authorship mark
  // on the reader's own document.
  //
  // Declared where the text is chosen rather than derived from `kind` at render time,
  // which is the same rule the evidence map already follows: the place that picks the
  // string is the only place that knows who wrote it.
  const built = read("lib", "scout-document-trace.ts");
  const quoted = [...built.matchAll(/summary: ([\w.]+),\n\s*\/\/[^\n]*\n\s*summaryMode: "quoted"/g)];
  assert.equal(quoted.length, 2, "the document-authored summaries no longer say so");
  assert.deepEqual(
    quoted.map((match) => match[1]),
    ["variable.document_target", "target.quote"],
    "a different pair of summaries is being called the document's words",
  );
  const panel = read("components", "scout-document-trace.tsx");
  assert.match(
    panel,
    /annotation\.summaryMode === "quoted" \? \(\s*<Quoted/,
    "the panel renders every summary the same way again",
  );
});

test("a priority states who wrote its statement, and the digest says it is a model's", () => {
  // Scout's grounding priorities quote the document's own target when there is one and
  // fall back to the model's sentence when there is not, so one field carries two authors
  // depending on the run. Rendered as a model's, the document's own words wore the
  // authorship mark - the tool claiming it wrote the reader's document.
  // Fixed by splitting the field rather than by labelling which author it holds: two
  // slots, `quote` for the document's words and `statement` for the model's, so every
  // row in one list has one shape instead of two.
  const selector = read("lib", "scout-priorities.ts");
  assert.ok(
    !/doc_target \|\| /.test(selector),
    "one field carries the document's words or the model's again, decided per run",
  );
  assert.match(selector, /quote: assessment\.doc_target/);
  assert.match(selector, /statement: assessment\.reason/);
  const panel = read("components", "ui", "priority-panel.tsx");
  assert.match(panel, /item\.quote && \(\s*<Quoted/, "the document's words are unmarked as quoted");
  assert.match(panel, /<Reading size="prominent">\{item\.statement\}/);
  // The digest is a model's summary of the list under it, and was the one paragraph on
  // the page most obviously written by a model that did not say so.
  assert.match(panel, /<Reading size="body" className="mb-4/, "the digest is unmarked again");
});

test("a marked sentence has one left edge", () => {
  // The mark is inline, so without a hanging indent the first line began after it and
  // every wrapped line fell back to the left of it - one sentence, two left edges - and
  // the `continued` note below, indented to clear the mark, lined up with neither.
  const text = read("components", "ui", "evidence-text.tsx");
  assert.match(
    text,
    /!continued && !inline && "pl-\[1\.5em\] -indent-\[1\.5em\]"/,
    "a marked sentence wraps back past its own mark",
  );
  assert.match(text, /continued && "pl-\[1\.5em\]"/, "the note no longer clears the mark");
});

test("the document's stated target is quoted wherever it is shown", () => {
  // The same text appeared twice with two treatments: ruled in the trace panel that opens
  // from this block, and plain full-contrast prose in the block itself. Plain prose is
  // the treatment for the tool's own words, so the card was presenting the reader's
  // document as though the tool had written it.
  //
  // `row.variable` stays plain on purpose: it is the row's heading, and the field title
  // above it - also the document's word - is not quoted either. A heading names the thing;
  // the quote is what the thing says.
  const page = read("app", "scout", "page.tsx");
  const block = page.slice(
    page.indexOf("<SectionLabel>Target stated in document</SectionLabel>"),
  );
  const body = block.slice(0, block.indexOf("</section>"));
  for (const field of ["row.minimum", "row.optimistic", "row.text"]) {
    const at = body.indexOf(`{${field}`);
    assert.ok(at > 0, `${field} is no longer rendered here`);
    assert.match(
      body.slice(Math.max(0, at - 220), at),
      /<Quoted/,
      `${field} is the document's own words and is not rendered as a quotation`,
    );
  }
});

test("every tool hands its run-identity readers the saved shape", () => {
  // `runLabel` and `runScope` read a *saved result*, which for every tool is an
  // envelope: `{ alignment: ... }`, `{ inspection: ... }`, `{ review: ... }`. Aligner's
  // view was handed the alignment inside its envelope, so both readers dereferenced
  // `undefined.documents` and the page threw a client-side exception on every run.
  //
  // Checked at the call site rather than by loosening the readers: a reader that accepts
  // either shape cannot tell a run it was given from one it was handed the inside of,
  // and would return a label built from nothing rather than failing.
  for (const tool of TOOLS) {
    const page = read("app", tool, "page.tsx");
    const call = page.match(new RegExp(`runScope\\((\\w+), "${tool}"\\)`));
    assert.ok(call, `${tool} does not name its run's configuration`);
    const held = call[1];
    // Whatever that identifier is, the same one must be what `runLabel` reads, and it
    // must not be the unwrapped inner result.
    assert.match(
      page,
      new RegExp(`runLabel\\(${held}, "${tool}"\\)`),
      `${tool} identifies its run from one object and scopes it from another`,
    );
    assert.ok(
      !new RegExp(`result=\\{[\\w.]*\\.(alignment|inspection|review)\\}`).test(page),
      `${tool} hands its view the inside of a saved result rather than the result`,
    );
  }
});

test("an Aligner finding carries one sentence, not two", () => {
  // `gap` sat beside `statement` on two verdicts, asked to name the distance from the
  // bar. The distance is not a third fact: it is the requirement and the statement, and
  // a reader has both - the requirement heads the row. What came back said so:
  //
  //   requirement  The target population minimum target is pregnant women 24-36 weeks.
  //   statement    The candidate sets the minimum as pregnant women at least 28 weeks.
  //   gap          Pregnant women 24-36 weeks required versus at least 28 weeks offered.
  //
  // The prompt said "do not restate the requirement". It restated the requirement on
  // every one of sixty-nine rows, because on a shortfall there is nothing else to say.
  for (const file of [
    ["lib", "api.ts"],
    ["lib", "aligner-chain.ts"],
    ["lib", "aligner-document-trace.ts"],
    ["app", "aligner", "page.tsx"],
  ] as const) {
    const source = read(...file);
    // The field, not the word: these files explain in prose what they no longer do,
    // and Tailwind's `gap-4` is a layout class.
    assert.ok(
      !/[.\s]gap:|\.gap\b/.test(source),
      `${file.join("/")} carries a second sentence per finding again`,
    );
  }
});

test("an Aligner requirement is a row, not a box inside a box", () => {
  // It was a bordered card inside a verdict group inside a collapsible card inside a
  // tab - the fourth box a reader counts down, and the nesting Inspector lost when a
  // unit stopped being a disclosure.
  const page = read("app", "aligner", "page.tsx");
  const row = page.slice(page.indexOf("function FindingRow"));
  const li = row.slice(row.indexOf("<li"), row.indexOf(">", row.indexOf("<li")));
  assert.ok(!/border/.test(li), "a finding draws its own box again");
  // And no help icon per row: sixty-nine of them, and an icon on one requirement cannot
  // say how a requirement differs from a verdict, which is what a reader gets wrong.
  assert.ok(
    !/AlignerSignalLabel topic="requirement"/.test(page),
    "the per-row help affordance is back",
  );
});

test("a mark is never rendered with nothing after it", () => {
  // A statement is empty where a tool has nothing to describe - Aligner's `not_addressed`
  // and Inspector's `specified`. Rendered anyway it is a four-pointed star followed by
  // blank space, which reads as a broken row rather than as silence.
  for (const [file, field] of [
    [["components", "aligner-document-trace.tsx"], "ref.statement"],
    [["components", "ui", "priority-panel.tsx"], "item.statement"],
    [["app", "inspector", "page.tsx"], "item.statement"],
  ] as const) {
    const source = read(...file);
    const at = source.indexOf(`{${field}}`);
    assert.ok(at > 0, `${field} is no longer rendered in ${file.join("/")}`);
    assert.match(
      source.slice(Math.max(0, at - 260), at),
      new RegExp(`${field.replace(".", "[.]")} && [(]`),
      `${file.join("/")} renders ${field} without checking it says anything`,
    );
  }
});

test("a how-to-read panel is a reference, not an essay", () => {
  // A popover a reader opens mid-task, so each topic has to be readable in one look.
  // Aligner's ran to 593 words across five topics and Screener's to 637 across four,
  // one of them 278 - four to five times Inspector's, which is short because collapsing
  // three vocabularies into one left it less to explain.
  //
  // The cap is per topic rather than per panel: a tool with five real distinctions
  // should be allowed five, and what makes a panel unreadable is one topic that turns
  // into prose, not the number of them.
  for (const tool of ["inspector", "scout", "aligner", "screener"]) {
    const source = read("components", `${tool}-signal-help.tsx`);
    const topics = [...source.matchAll(/title: "([^"]+)"[\s\S]*?detail:\s*\n?\s*"([^"]+)"/g)];
    assert.ok(topics.length > 0, `${tool} publishes no topics`);
    for (const [, title, detail] of topics) {
      const words = detail.split(/\s+/).length;
      assert.ok(
        words <= 90,
        `${tool}'s "${title}" runs to ${words} words; a topic a reader takes in at a `
          + "glance is under ninety",
      );
    }
  }
});

test("both sides of a comparison say which document they came from", () => {
  // A row holds two model sentences - the bar read out of one document, the answer read
  // out of the other - and they are deliberately parallel so the difference is legible:
  // "24-36 wks" beside "at least 28 weeks". Neither is a quotation, because the
  // extractor is asked for "one short sentence stating the requirement in the document's
  // own terms", which is the model's words carrying the document's numbers. A left rule
  // on the first would claim a verbatimness the pipeline never promised, and marking
  // both as a model's leaves nothing to tell them apart.
  //
  // What separates them is which document, so each line leads with its name. That used
  // to sit at the bottom of the row on two triggers both reading "In document".
  const page = read("app", "aligner", "page.tsx");
  assert.match(
    page,
    /<Attributed\s+document=\{referenceName\}/,
    "the bar does not say which document states it",
  );
  assert.match(
    page,
    /<Attributed\s+document=\{comparisonName\}/,
    "the answer does not say which document it was read from",
  );
  assert.ok(
    !/<Quoted[^>]*>\{finding\.requirement\}/.test(page),
    "a requirement is ruled as a quotation, which the extractor never promises",
  );
});

test("every tool reports its outcome through the one metrics row", () => {
  // Four tools, four shapes for one question - how did this run come out. Inspector drew
  // dotted counts anchored to nothing, Aligner put a help icon on its denominator,
  // Screener used a `dl` of value-label pairs with neither dot nor total and then
  // restated the total in a closing paragraph, and Scout wrote prose.
  //
  // The first fix made three of them *contain* the right parts, which is not the same as
  // their being the same shape - Screener still stacked its total above its dots while
  // the other two put them on one line, and this test passed. Containment was the wrong
  // thing to assert. The row is now a component, so the shape is an argument rather than
  // an arrangement, and what is left to check is that nobody re-implements it.
  for (const tool of ["inspector", "aligner", "screener", "scout"]) {
    const page = read("app", tool, "page.tsx");
    const start = Math.max(
      page.indexOf("function RunCoverage"),
      page.indexOf("function CountRow"),
    );
    const body = page.slice(start, page.indexOf("\n}\n", start));
    assert.match(body, /<MetricsRow/, `${tool} builds its own metrics panel`);
    assert.match(
      body,
      /total=\{/,
      `${tool} shows counts with no denominator, so a figure is anchored to nothing`,
    );
    assert.match(body, /items=\{/, `${tool} states no distribution over its denominator`);
    // Whether a figure is inside the distribution or outside it is the one judgement the
    // row cannot make for a tool: Inspector's cross-section conflicts and Screener's
    // required-and-open count are true of the run and are not buckets, and either one
    // standing in the row would break the sum a reader was invited to check.
    assert.ok(
      !/<VerdictCounts/.test(body),
      `${tool} draws the distribution itself, beside the row that exists to draw it`,
    );
  }
});

test("the metrics panel carries no help affordance", () => {
  // `ResultLayout` requires a `metricsNote`, which opens the panel with a sentence saying
  // what the figures count. A tooltip inside answers a question the reader had answered
  // three lines above. Aligner had one on its denominator and Screener one on its aside,
  // and the first pass removed only Aligner's - because the check was written against
  // Aligner by name rather than against the rule.
  for (const tool of ["inspector", "aligner", "screener", "scout"]) {
    const page = read("app", tool, "page.tsx");
    const start = Math.max(
      page.indexOf("function RunCoverage"),
      page.indexOf("function CountRow"),
    );
    const body = page.slice(start, page.indexOf("\n}\n", start));
    assert.ok(
      !/SignalLabel|SignalHelp/.test(body),
      `${tool}'s metrics panel explains itself twice`,
    );
  }
  // And the note actually says what the row sums to, which is the sentence the tooltips
  // were standing in for.
  for (const tool of ["inspector", "aligner", "screener", "scout"]) {
    assert.match(
      read("app", tool, "page.tsx"),
      /metricsNote="[^"]*(sums to|by verdict|by state|including the classes)/,
      `${tool} never says what its figures count`,
    );
  }
});

test("one tone decision per vocabulary, wherever it is drawn", () => {
  // Screener's question states carried their own background classes inside the coverage
  // strip - a fifth tone vocabulary beside the four on the shared scale, and unreachable
  // from the metrics row, which is why its counts were the only ones with no dot.
  //
  // The grid still fills a cell where a row draws a dot; what moved is the *decision*
  // about which state is which tone.
  const api = read("lib", "api.ts");
  assert.match(api, /QUESTION_STATE_TONE: Record<QuestionState, Tone>/);
  const strip = read("components", "screener-coverage-strip.tsx");
  assert.ok(
    !/cell: "bg-\[hsl/.test(strip),
    "the coverage strip decides its own tones again",
  );
  assert.match(strip, /QUESTION_STATE_TONE\[/, "the strip no longer reads the shared tone");
  // Silence is neutral in both tools that have a word for it: Aligner's `not_addressed`
  // and Screener's `not_found` both say the material says nothing, which is not a failure.
  assert.match(api, /not_found: "neutral"/);
  assert.match(api, /not_addressed: "neutral"/);
});
