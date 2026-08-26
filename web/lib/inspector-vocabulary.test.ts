/**
 * Binds Inspector's published vocabulary to the service that owns it.
 *
 * A verdict crosses the layer boundary as a string. Without this test the web layer
 * keeps rendering whatever it last hardcoded, so a value the service added would
 * arrive unlabelled and one it removed would keep a dead branch.
 *
 * One vocabulary, where there used to be three - a reason, a level looked up from the
 * reason, and a status that bucketed the levels. This file bound all three, which is
 * how it stayed true while the interface showed "Insufficient" on a finding and
 * "Not met" on the unit above it and called them different fields.
 *
 * Same mechanism as `document-formats.test.ts`: the service declares, the web layer
 * mirrors, and a test fails when the two disagree.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";

import {
  ASSESSED_VERDICTS,
  VERDICTS,
  VERDICT_DESCRIPTION,
  VERDICT_LABEL,
  verdictLabel,
} from "./api.ts";

const REPO = path.resolve(import.meta.dirname, "..", "..");
const MODELS = path.join(REPO, "services", "inspector", "models.py");

function declaredTuple(name: string): string[] {
  const source = readFileSync(MODELS, "utf8");
  const declaration = new RegExp(`^${name}[^=]*=\\s*\\(([^)]*)\\)`, "m").exec(source);
  assert.ok(declaration, `${name} is no longer declared as a tuple literal`);
  return [...declaration[1].matchAll(/"([^"]+)"|'([^']+)'/g)].map(
    (match) => match[1] ?? match[2],
  );
}

test("the verdicts match services/inspector, in the same order", () => {
  // Order is part of the contract: it is worst-first after `specified`, and the
  // document trace's layer list, the worklist's ranking and a section's count row all
  // read that order rather than keeping a second one.
  assert.deepEqual([...VERDICTS], declaredTuple("VERDICTS"));
});

test("there is one axis, and no second one has grown back", () => {
  const source = readFileSync(MODELS, "utf8");
  for (const gone of [
    "FINDING_REASONS",
    "FINDING_LEVELS",
    "LEVEL_BY_REASON",
    "UNIT_STATUSES",
  ]) {
    assert.ok(
      !source.includes(`${gone} `),
      `${gone} is declared again, so one judgement has two vocabularies`,
    );
  }
});

test("every published value has a label and a description", () => {
  for (const verdict of VERDICTS) {
    // Both, because a verdict names itself and explains itself separately: a label
    // short enough for a pill, and the sentence behind it.
    assert.ok(VERDICT_LABEL[verdict], `${verdict} has no label`);
    assert.ok(VERDICT_DESCRIPTION[verdict], `${verdict} has no description`);
  }
});

test("what needs work is a subset of the one axis, not a second list", () => {
  for (const verdict of ASSESSED_VERDICTS) {
    assert.ok(VERDICTS.includes(verdict), `${verdict} is not a published verdict`);
  }
  assert.deepEqual(
    VERDICTS.filter((verdict) => !ASSESSED_VERDICTS.includes(verdict)),
    ["specified", "not_applicable"],
    "the rubric satisfied and the rubric not asking are the only two that are not work",
  );
});

test("one concept has one name, with no alias to choose between", () => {
  // `adherence` used to render as "Adherence" from a raw key in one place and
  // "Template adherence" from a hand-kept map in two others.
  const labels = Object.values(VERDICT_LABEL);
  assert.equal(new Set(labels).size, labels.length, "two values share a label");
});

test("a verdict key is named the way it renders", () => {
  // The keys used to collide across the two axes they spanned: the reason `unmet`
  // rendered as "Insufficient" while the status `not_met` rendered as "Not met", so a
  // reader of the code had to remember which near-identical key meant which.
  assert.ok(!VERDICTS.includes("unmet" as never));
  assert.ok(!VERDICTS.includes("not_met" as never));
  assert.ok(!VERDICTS.includes("missing" as never));
  assert.ok(!VERDICTS.includes("unclear" as never));
});

test("no label asserts a consequence the tool cannot see", () => {
  // The scale this replaced said "Critical", which is a claim about what a
  // shortfall costs. Inspector knows what the rubric asked and what the document
  // supplies; it does not know the programme.
  const forbidden = /critical|urgent|severe|must|blocker|priority/i;
  for (const text of [
    ...Object.values(VERDICT_LABEL),
    ...Object.values(VERDICT_DESCRIPTION),
  ]) {
    assert.ok(!forbidden.test(text), `"${text}" asserts a consequence`);
  }
});

test("an unrecognised verdict renders as itself rather than as nothing", () => {
  // The boundary rule: the web layer reads a verdict through a lookup, never a
  // branch, so a verdict added upstream degrades to its own name instead of
  // rendering blank or failing to compile.
  assert.equal(verdictLabel("some_new_verdict"), "some_new_verdict");
  assert.equal(verdictLabel("vague"), VERDICT_LABEL.vague);
});
