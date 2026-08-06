/**
 * Binds Inspector's published vocabulary to the service that owns it.
 *
 * A reason, a level, and a status cross the layer boundary as strings. Without this
 * test the web layer keeps rendering whatever it last hardcoded, so a value the
 * service added would arrive unlabelled and one it removed would keep a dead branch.
 *
 * Same mechanism as `document-formats.test.ts`: the service declares, the web layer
 * mirrors, and a test fails when the two disagree.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";

import {
  FINDING_LEVELS,
  FINDING_REASONS,
  LEVEL_LABELS,
  REASON_LABELS,
  STATUS_LABELS,
  UNIT_STATUSES,
  reasonLabel,
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

test("the reasons match services/inspector, in the same order", () => {
  // Order is part of the contract: it is worst-first, and both the document
  // trace's layer list and a unit's finding list read that order rather than
  // keeping a second one.
  assert.deepEqual([...FINDING_REASONS], declaredTuple("FINDING_REASONS"));
});

test("the levels and statuses match services/inspector", () => {
  assert.deepEqual([...FINDING_LEVELS], declaredTuple("FINDING_LEVELS"));
  assert.deepEqual([...UNIT_STATUSES], declaredTuple("UNIT_STATUSES"));
});

test("every published value has a label, so none renders as a raw key", () => {
  for (const reason of FINDING_REASONS) {
    assert.ok(REASON_LABELS[reason], `${reason} has no label`);
  }
  for (const level of FINDING_LEVELS) {
    assert.ok(LEVEL_LABELS[level], `${level} has no label`);
  }
  for (const status of UNIT_STATUSES) {
    assert.ok(STATUS_LABELS[status], `${status} has no label`);
  }
});

test("one concept has one name, with no alias to choose between", () => {
  // `adherence` used to render as "Adherence" from a raw key in one place and
  // "Template adherence" from a hand-kept map in two others.
  const labels = [
    ...Object.values(REASON_LABELS),
    ...Object.values(LEVEL_LABELS),
  ];
  assert.equal(new Set(labels).size, labels.length, "two values share a label");
});

test("no label asserts a consequence the tool cannot see", () => {
  // The scale this replaced said "Critical", which is a claim about what a
  // shortfall costs. Inspector knows what the rubric asked and what the document
  // supplies; it does not know the programme.
  const forbidden = /critical|urgent|severe|must|blocker|priority/i;
  for (const text of [
    ...Object.values(REASON_LABELS),
    ...Object.values(LEVEL_LABELS),
    ...Object.values(STATUS_LABELS),
  ]) {
    assert.ok(!forbidden.test(text), `"${text}" asserts a consequence`);
  }
});

test("an unrecognised reason renders as itself rather than as nothing", () => {
  // The boundary rule: the web layer reads a reason through a lookup, never a
  // branch, so a reason added upstream degrades to its own name instead of
  // rendering blank or failing to compile.
  assert.equal(reasonLabel("some_new_reason"), "some_new_reason");
  assert.equal(reasonLabel("missing"), REASON_LABELS.missing);
});
