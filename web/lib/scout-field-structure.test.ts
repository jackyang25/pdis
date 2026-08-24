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
