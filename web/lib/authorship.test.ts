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
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";

const REPO = path.resolve(import.meta.dirname, "..");
const read = (...parts: string[]) => readFileSync(path.join(REPO, ...parts), "utf8");

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
  assert.match(page, /<Reading size="prominent">\{finding\.statement\}<\/Reading>/);
  assert.match(page, /<Reading>\{finding\.recommendation\}<\/Reading>/);
});

test("one verdict has one appearance", () => {
  // "Met" rendered as a tinted pill on a unit and as muted text on a section, so the same
  // verdict looked like good news in one row and like an absence in the row above it.
  const page = read("app", "inspector", "page.tsx");
  assert.ok(
    !/return <span className="text-xs text-muted-foreground">Met<\/span>;/.test(page),
    "a section states Met in its own words instead of the shared pill",
  );
  assert.match(page, /<StatusPill status="met" \/>/);
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
  const help = readFileSync(path.join(REPO, "components", "inspector-signal-help.tsx"), "utf8");
  assert.match(help, /terms: FINDING_REASONS\.map/, "the reasons are not itemised");
  assert.match(help, /terms: UNIT_STATUSES\.map/, "the statuses are not itemised");
});

test("the panel reads the labels rather than restating them", () => {
  // A retyped list is a second copy that drifts. Built from the maps, the panel cannot
  // come to explain a word the interface no longer uses.
  const help = readFileSync(path.join(REPO, "components", "inspector-signal-help.tsx"), "utf8");
  assert.match(help, /term: REASON_LABELS\[reason\]/);
  assert.match(help, /meaning: REASON_DESCRIPTION\[reason\]/);
});

test("every reason has a short label and a full description", () => {
  // The split statuses already have. A reason renders as an inline chip and as the options
  // of the trace's layer selector, where a five-word sentence wrapped onto two lines.
  const api = readFileSync(path.join(REPO, "lib", "api.ts"), "utf8");
  const labels = api.match(/export const REASON_LABELS[\s\S]*?\n\};/)?.[0] ?? "";
  const descriptions = api.match(/export const REASON_DESCRIPTION[\s\S]*?\n\};/)?.[0] ?? "";
  assert.ok(descriptions, "reasons have no description map");
  const keys = (block: string) => (block.match(/^\s{2}(\w+):/gm) ?? []).map((k) => k.trim());
  assert.deepEqual(keys(labels), keys(descriptions), "the two maps cover different reasons");
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
  for (const tool of ["scout", "inspector", "aligner", "expert"]) {
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
