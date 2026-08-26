/**
 * The four result axes are peers, so a field row renders them as peers.
 *
 * They had drifted into four different presentations of the same idea. Two showed a verdict
 * on the right of the heading, one showed a count, one showed nothing. Counts appeared in
 * three places: on the right of a heading, inline in a group row, and as loose text under a
 * sentence. And two of the four could be opened while two could not, so a reader could not
 * tell that "Grounding 7 insights" and "Conflicts 2" meant the same kind of thing.
 *
 * These tests hold the skeleton, not the styling: one heading, one headline beside it, and
 * groups in one row shape.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";

const PAGE = readFileSync(
  path.resolve(import.meta.dirname, "..", "app", "scout", "page.tsx"),
  "utf8",
);

/** JSX comments carry the reasoning and are long, so proximity is measured without them. */
const CODE = PAGE.replaceAll(/\{\/\*[\s\S]*?\*\/\}/g, "").replaceAll(/\/\*[\s\S]*?\*\//g, "");

/**
 * The two axes whose heading is written where it is rendered.
 *
 * The other two reach `SectionLabel` as a `label` prop on `SignalVerdict`, so their headline
 * is checked once, in that component, rather than at each call site.
 */
const LITERAL_AXES = ["Measurable targets", "Relation to document target"];

/**
 * One function's source, from its declaration to the next top-level one.
 *
 * Not "up to the next line starting with a brace": a destructured parameter list closes with
 * one, so that stopped at the signature and the first version of these tests was asserting
 * against an empty body.
 */
function functionBody(source: string, name: string): string {
  const start = source.indexOf("function " + name + "(");
  assert.ok(start > 0, "no function named " + name);
  const after = source.slice(start + 1);
  const end = after.search(/\n(function |\/\*\*|export )/);
  return end < 0 ? after : after.slice(0, end);
}

test("every axis heading has a headline beside it", () => {
  // The relation section was the only one with nothing on the right, which made it read as a
  // list of controls rather than as a fourth reading of the field.
  const withoutHeadline = LITERAL_AXES.filter((axis) => {
    const at = CODE.indexOf(`>${axis}</SectionLabel>`);
    assert.ok(at > 0, `no heading renders "${axis}"`);
    return !CODE.slice(Math.max(0, at - 200), at).includes("justify-between");
  });
  assert.deepEqual(withoutHeadline, [], "an axis heading has no headline beside it");

  // Grounding and Precedent, both of which render through here.
  const body = functionBody(CODE, "SignalVerdict");
  assert.match(body, /justify-between/);
  assert.match(body, /<SectionLabel>\{label\}<\/SectionLabel>/);
  assert.match(body, /chips\.map/, "a verdict has no headline chip beside its heading");
});

test("groups inside a field use one row shape", () => {
  // Four hand-written `<summary>` rows existed for the same idea. `DisclosureRow` owns the
  // chevron, the optional tone dot, the label and the count.
  assert.match(PAGE, /function DisclosureRow\(/);
  // Three call sites, not four rows: the relation buckets and the two verdict citations are
  // each a `.map`, so the row count is data and the call count is what can be asserted.
  const uses = PAGE.match(/<DisclosureRow/g) ?? [];
  assert.equal(uses.length, 3, "an in-field group is drawing its own row again");
  // `group-open/disp` was the numbers-not-used-as-targets row. `group-open/rel` still exists
  // in the projections tab, which is a page-level row of a different tier, not an in-field
  // group, so it is deliberately not checked here.
  assert.ok(
    !PAGE.includes("group-open/disp"),
    "a hand-written group row is back (group-open/disp)",
  );
});

test("a verdict's citation opens, like every other group", () => {
  // It used to be loose text: "7 insights", above a list of 63, with no way to see which 7.
  assert.match(PAGE, /function CitedInsightIndex\(/);
  assert.ok(
    !PAGE.includes("function CitationNote"),
    "the unopenable count is back alongside the openable one",
  );
});

test("a citation is an index, not a second copy of the insight", () => {
  // 911 insights exist; grounding and precedent cite 628 between them. Drawing those in full
  // would restore most of the duplication this view was rebuilt to remove, so a citation is
  // one line per insight that links to the single full record.
  const body = functionBody(PAGE, "CitedInsightIndex");
  assert.ok(!body.includes("<EvidenceProvenance"), "a citation redraws an insight's sources");
  assert.ok(!body.includes("<DocumentSourceTrace"), "a citation redraws an insight's passage");
  assert.match(body, /insightAnchor\(match\)/, "a citation does not link to the full record");
});

test("the full insight is drawn in exactly one place", () => {
  // The anchor is what a citation points at, so a second copy would duplicate a DOM id and
  // break the link as well as the reading.
  const anchors = PAGE.match(/id=\{insightAnchor\(match\)\}/g) ?? [];
  assert.equal(anchors.length, 1, "an insight anchor is rendered in more than one place");
  const provenance = PAGE.match(/<EvidenceProvenance/g) ?? [];
  assert.equal(provenance.length, 1, "an insight's sources are drawn in more than one place");
});

test("a citation that lands on a closed row opens it", () => {
  // Both the hash and the click, because clicking a citation whose hash is already current
  // fires no `hashchange`.
  assert.match(PAGE, /function revealInsight\(/);
  assert.match(PAGE, /onClick=\{\(\) => revealInsight\(/);
  assert.match(PAGE, /addEventListener\("hashchange"/);
  const body = functionBody(PAGE, "revealInsight");
  assert.match(body, /while \(ancestor\)/, "only the nearest details is opened, not every one");
});

test("every full-width row that opens uses one shape", () => {
  // Four of these existed across four tabs and three agreed. The safety row had a lighter
  // hover, a stronger focus ring, a fainter open tint, no focus background and a minimum
  // height, none of which marked a difference in what the row does.
  // Now in `lib/expandable-row.ts`, because Inspector needed it too: it rendered all 32 of
  // its units expanded at once while Scout collapsed 28 fields, which is the same row doing
  // opposite things in two tools.
  const shape = readFileSync(
    path.resolve(import.meta.dirname, "expandable-row.ts"),
    "utf8",
  );
  assert.match(shape, /export const EXPANDABLE_ROW =/);
  assert.ok(!/const EXPANDABLE_ROW =/.test(PAGE), "Scout kept its own copy of the shape");
  // Shared, not tallied. This asserted a literal 5, which only ever failed when a row was
  // deliberately deleted - a row *added* without the constant leaves the count untouched,
  // so the number never caught the thing the test is named for. What it can check is that
  // the shape has more than one tool using it.
  const users = ["scout", "inspector"].filter((tool) =>
    readFileSync(
      path.resolve(import.meta.dirname, "..", "app", tool, "page.tsx"),
      "utf8",
    ).includes("EXPANDABLE_ROW"),
  );
  assert.deepEqual(users, ["scout", "inspector"], "a tool stopped using the shared row shape");
  // The per-tab group scopes those rows used. A row keeping its own scope is how one would
  // half-adopt the shape: same classes, its own open state.
  for (const scope of ["indicator", "program", "safety", "field"]) {
    assert.ok(
      !PAGE.includes(`group-open/${scope}:`),
      `a full-width row kept its own open scope (${scope})`,
    );
  }
});

test("every panel behind a provenance trigger opens the same way", () => {
  // Four panels, one header, one width. The distribution plot's popover is deliberately not
  // one of them: it is a 300px card describing a single point under the cursor, not a panel
  // listing entries, so it has no eyebrow, title and description to place.
  const panels = [
    "components/evidence-provenance.tsx",
    "components/excluded-measurements.tsx",
    "components/comparator-cohort.tsx",
    "components/document-source-trace.tsx",
    "components/field-searches.tsx",
  ];
  for (const file of panels) {
    const text = readFileSync(path.resolve(import.meta.dirname, "..", file), "utf8");
    assert.match(text, /TracePanelHeader/, `${file} heads its panel by hand`);
    // The geometry is a constant now. It was four copies of the width and three of the
    // scroll height, beside near-variants at 58vh and 76vh.
    assert.match(text, /PROVENANCE_PANEL\.width/, `${file} opens at its own width`);
    assert.match(text, /PROVENANCE_PANEL\.scroll/, `${file} scrolls at its own height`);
    assert.match(text, /<ProvenanceTrigger/, `${file} draws its own trigger`);
  }
});

test("the statistics grid draws no rules it cannot finish", () => {
  // The rules were per cell, with `last:border-r-0` for the right edge and an
  // `nth-last-child(-n+3)` rule for the bottom one. Both encode "three columns" in a grid that
  // has two at narrow widths and two or three at wide ones, so at two columns the second cell
  // kept a right border with nothing beyond it and lost the bottom border it needed. The
  // column count answers to the content, so a selector cannot know it.
  const body = functionBody(PAGE, "StatCell");
  assert.ok(!body.includes("border-r"), "a cell draws its own vertical rule again");
  assert.ok(!body.includes("border-b"), "a cell draws its own horizontal rule again");
  assert.ok(
    !body.includes("nth-last-child"),
    "a cell is positioning itself by a column count a selector cannot see",
  );
});

test("the run's source count covers every place a source is cited", () => {
  // Measured on a real run: insights, verdicts and measurements share 671 distinct sources,
  // and development and safety records bring it to 827. Dropping one of these collections
  // would narrow the headline silently, since it would still look like a plausible number.
  const body = functionBody(PAGE, "distinctSourceCount");
  for (const collection of [
    "result.matches",
    "result.assessments",
    "result.precedents",
    "result.conformity",
    "result.development_landscape",
    "result.safety_observations",
  ]) {
    assert.ok(body.includes(collection), `the source count skips ${collection}`);
  }
});

test("the headline says which scope each of its numbers has", () => {
  // "827 sources · 911 insights" under a title reading "28 fields" invited reading both as
  // field-scoped. One is: insights are bound to a field. The other is not.
  //
  // The two numbers moved out of the subtitle and into the metrics panel, so the sentence
  // that separates them moved with them - into `metricsNote`, which is the panel's first
  // line. The rule is unchanged: wherever the two counts are shown, the reader is told
  // they do not share a denominator.
  const note = PAGE.match(/metricsNote="([^"]+)"/);
  assert.ok(note, "Scout states no note on what its figures count");
  assert.match(note[1], /within fields/);
  assert.match(note[1], /whole run/);
});

test("a count is one size, wherever it appears", () => {
  // Ten counts, nine at 11px and one a size larger on a safety row. Nothing about that row
  // makes its count a different kind of number.
  const sizes = new Set(
    [...PAGE.matchAll(/className="([^"]*\btabular-nums\b[^"]*)"/g)]
      .map((match) => match[1])
      // The target's own value is deliberately larger: it is the subject of its row, not a
      // count of things in it.
      .filter((value) => !value.includes("text-foreground"))
      .map((value) => value.match(/text-(?:\[11px\]|xs|sm|base)/)?.[0] ?? "none"),
  );
  assert.deepEqual([...sizes], ["text-[11px]"], "a count picked its own size");
});

test("an arrival is marked with the shared ring, not just scrolled to", () => {
  // Opening the bucket is not enough: on a real run the largest bucket holds 43 insights and
  // the one that was cited lands mid-screen looking exactly like its neighbours. Same recipe
  // as a jump into a document passage, imported rather than restyled, which
  // `motion-standard.test.ts` also enforces from the other direction.
  const body = functionBody(PAGE, "revealInsight");
  assert.match(body, /ARRIVAL_HIGHLIGHT\b/);
  assert.match(body, /ARRIVAL_HIGHLIGHT_MS/, "the hold is hand-picked instead of standard");
  assert.match(body, /clearTimeout/, "two jumps in a row leave two rings behind");
  assert.match(
    body,
    /prefers-reduced-motion/,
    "the scroll animates even for a reader who asked it not to",
  );
});

test("the retrieval record is reachable, and not summarised in its place", () => {
  // `search_plan` held 754 traces on a real run and rendered nowhere. `Sources` is per
  // insight, so it can only show a search that found something: 229 of 529 distinct queries,
  // with 300 invisible. Those 300 are what makes a negative verdict readable, since
  // "Unsupported" means opposite things depending on whether a field was searched sixty ways
  // or barely touched.
  assert.match(PAGE, /<FieldSearches/, "a field does not offer its retrieval record");
  assert.match(PAGE, /searchPlan=\{result\.search_plan\}/);

  // The line it replaced. That named an entity which appeared in 4 of the 62 searches for
  // its field, so it claimed the aiming of a search it mostly did not aim, and it carried
  // the evidence domain behind a gate that was not about the evidence domain.
  // Comment-stripped: the comment explaining why it went names the string it replaced.
  assert.ok(
    !CODE.includes("Searched by "),
    "the entity summary is back in place of the record",
  );
});

test("every field states which body of evidence it was searched as", () => {
  // It was true of all 28 fields and visible on 3, because it rode the entity gate.
  assert.match(PAGE, /\{dimensionLabel\(evidenceDomain\)\} evidence/);
  const at = PAGE.indexOf("{dimensionLabel(evidenceDomain)} evidence");
  const before = PAGE.slice(Math.max(0, at - 400), at);
  assert.ok(
    !/entities\.length > 0 && \($/.test(before.trim()),
    "the domain is gated on something that is not the domain again",
  );
});

test("a field row threads no prop it does not render", () => {
  // `entities` survived the line it fed as a prop on the call site, on the parameter list and
  // in the type, reaching nothing. A dead prop is worse than dead code: it reads as data the
  // row uses, so the next reader threads a fourth thing beside it.
  const declared = [...PAGE.matchAll(/^  ([a-z][A-Za-z0-9]*),$/gm)].map((m) => m[1]);
  const body = PAGE.slice(PAGE.indexOf("function FieldRow("));
  const unread = declared.filter((name) => {
    if (!new RegExp(`^  ${name},$`, "m").test(body)) return false;
    // Once as the parameter, once in the type, once at the call site. Anything that is read
    // appears a fourth time.
    const uses = [...PAGE.matchAll(new RegExp(`\\b${name}\\b`, "g"))].length;
    return uses <= 3;
  });
  assert.deepEqual(unread, [], "a prop is threaded into FieldRow and never read");
});
