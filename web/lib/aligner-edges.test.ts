import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { test } from "node:test";

import { edgeApplies, type AlignmentEdgeSpec } from "./api.ts";

/**
 * The shipped chain, plus the link that stands in for a missing one.
 *
 * A fixture, because what is under test is the rule rather than the config. But it is a
 * hand-copy of `configs/alignment.yaml`, and a fixture that has quietly stopped matching
 * the thing it stands for is worse than no fixture: these cases would keep passing while
 * the shipped config no longer declared the fallback at all. The test below reads the
 * real file and refuses that.
 */
const DECLARED: AlignmentEdgeSpec[] = [
  { reference: "itpp", comparison: "ctpp", question: "a" },
  { reference: "ctpp", comparison: "ipdp", question: "b" },
  { reference: "itpp", comparison: "ipdp", question: "c", when_absent: "ctpp" },
];

const CONFIG = readFileSync(
  path.resolve(
    import.meta.dirname,
    "..",
    "..",
    "services",
    "aligner",
    "configs",
    "alignment.yaml",
  ),
  "utf8",
);

const applied = (chosen: string[]) =>
  DECLARED.filter((edge) => edgeApplies(edge, chosen)).map(
    (edge) => `${edge.reference}-to-${edge.comparison}`,
  );

test("a profile and a plan with nothing between them compare directly", () => {
  // The case that failed outright: the declared comparisons form a chain, and with the
  // middle document missing neither pair resolved, so the run raised rather than
  // comparing the two documents it had. It is the commonest two-document pairing after
  // iTPP/cTPP — a programme often has a profile and a plan before a candidate profile is
  // written — and a plan really is written against the Foundation's profile when there is
  // no candidate profile to sit between them.
  assert.deepEqual(applied(["itpp", "ipdp"]), ["itpp-to-ipdp"]);
});

test("the middle document supersedes the direct comparison", () => {
  // A fallback, not a third comparison. With all three, iTPP-to-IPDP reports differences
  // the two-step chain already explains, and a reader would meet one shortfall twice
  // under two questions.
  assert.deepEqual(applied(["itpp", "ctpp", "ipdp"]), [
    "itpp-to-ctpp",
    "ctpp-to-ipdp",
  ]);
});

test("the unconditional pairs are unaffected", () => {
  assert.deepEqual(applied(["itpp", "ctpp"]), ["itpp-to-ctpp"]);
  assert.deepEqual(applied(["ctpp", "ipdp"]), ["ctpp-to-ipdp"]);
});

test("the picker resolves comparisons the way the service does", () => {
  // Two places apply this rule: the service, to build a run, and the picker, to say what
  // a run would compare before there is one. The picker had the rule inline as a pair of
  // `includes` calls, so the condition would have had to be remembered twice — and the
  // failure that produces is a preview promising a comparison the run then skips.
  const page = readFileSync(
    path.resolve(import.meta.dirname, "..", "app", "aligner", "page.tsx"),
    "utf8",
  );
  assert.match(page, /declaredEdges\.filter\(\(edge\) => edgeApplies\(edge, chosen\)\)/);
  assert.ok(
    !/chosen\.includes\(edge\./.test(page),
    "the picker decides for itself which comparisons a run would make",
  );
});

test("the fixture above is the config that ships", () => {
  // Read as text rather than parsed: the point is that the three declared pairs and the
  // one condition are really there, and a YAML parser in the web suite to check three
  // lines would be a dependency for the sake of one test.
  for (const { reference, comparison, when_absent } of DECLARED) {
    const declared = new RegExp(
      `- reference: ${reference}\\s+comparison: ${comparison}\\s+question: [^\\n]+`
        + (when_absent ? `\\s+when_absent: ${when_absent}` : ""),
    );
    assert.match(
      CONFIG,
      declared,
      `the config no longer declares ${reference} to ${comparison}`
        + (when_absent ? ` conditional on ${when_absent}` : ""),
    );
  }
  // And nothing else is declared, so a fourth pair cannot appear without these cases
  // being reconsidered - the rule is about which comparisons a set of documents makes,
  // and a new pair changes every answer above.
  assert.equal(
    (CONFIG.match(/^  - reference:/gm) ?? []).length,
    DECLARED.length,
    "the config declares a comparison these cases do not cover",
  );
});
