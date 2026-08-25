/**
 * The rules Scout's vocabulary already follows, applied to every tool's.
 *
 * `scout-labels.test.ts` checks nine maps for internal vocabulary, empty or duplicated
 * entries, and length. Inspector's and Aligner's maps live in `lib/api.ts` and were checked
 * by nothing, which is how a thirteen-word sentence came to render as an inline pill.
 *
 * This file holds the rules that are the same for every tool. Scout keeps its own file for
 * the checks that are Scout-specific: the glossary binding, the tooltip titles, the
 * how-to-read panel.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";

import {
  LEVEL_LABELS,
  REASON_LABELS,
  STATUS_LABEL,
  VERDICT_LABELS,
} from "./api.ts";
import {
  CALIBRATION_BASIS_LABEL,
  DISPOSITION_LABEL,
  GROUNDING_LABEL,
  OUTCOME_LABEL,
  PRECEDENT_LABEL,
  RELATIONSHIP_LABEL,
  SEMANTIC_STATUS_LABEL,
  SOURCE_IDENTITY_CAVEAT,
  TARGET_ROLE_LABEL,
} from "./scout-labels.ts";
import { relationshipLabel, sourceRoleLabel } from "./scout-projection-roles.ts";

/**
 * Every map whose values a reader sees, across the suite.
 *
 * A map belongs here the moment a value of it renders. The ones reached through a function
 * are spread out by hand rather than exported, so adding a case cannot quietly skip these.
 */
const VOCABULARY: Record<string, Record<string, string>> = {
  // Scout
  RELATIONSHIP_LABEL,
  GROUNDING_LABEL,
  PRECEDENT_LABEL,
  OUTCOME_LABEL,
  DISPOSITION_LABEL,
  SEMANTIC_STATUS_LABEL,
  CALIBRATION_BASIS_LABEL,
  TARGET_ROLE_LABEL,
  SOURCE_IDENTITY_CAVEAT,
  PROJECTION_RELATIONSHIP: Object.fromEntries(
    (["direct", "analogous", "adjacent", "unrelated", "unknown"] as const).map((k) => [
      k,
      relationshipLabel(k),
    ]),
  ),
  SOURCE_ROLE: Object.fromEntries(
    (["experimental", "comparator", "control", "co_intervention", "unknown"] as const).map(
      (k) => [k, sourceRoleLabel(k)],
    ),
  ),
  // Inspector and Aligner
  REASON_LABELS,
  LEVEL_LABELS,
  VERDICT_LABELS,
  STATUS_LABEL,
};

/**
 * Words that name how the system works rather than what the reader is looking at.
 *
 * Same list Scout's own test uses. A label carrying one of these asks a reader to know an
 * internal before they can read a result.
 */
const INTERNAL = [
  "calibrat",
  "scalar",
  "atomic",
  "ledger",
  "conformity",
  "projection",
  "claim-compatible",
  "basis of",
  "disposition",
  "semantic slot",
];

test("no label asks the reader to know the tool's internals", () => {
  const offenders: string[] = [];
  for (const [name, map] of Object.entries(VOCABULARY)) {
    for (const [key, label] of Object.entries(map)) {
      for (const word of INTERNAL) {
        if (label.toLowerCase().includes(word)) offenders.push(`${name}.${key}: "${label}"`);
      }
    }
  }
  assert.deepEqual(offenders, []);
});

test("no label is empty, and none repeats another within its own map", () => {
  for (const [name, map] of Object.entries(VOCABULARY)) {
    const values = Object.values(map);
    for (const label of values) assert.ok(label.trim(), `${name} has an empty label`);
    assert.equal(
      new Set(values).size,
      values.length,
      `${name} uses one label for two states`,
    );
  }
});

test("every label is short enough to sit inline beside a value", () => {
  // Five words. These render in a chip, a pill, or a cell beside a number, and a label that
  // wraps there is a sentence in the wrong place: Inspector rendered "The rubric asks for
  // this and the document does not usably supply it" as an inline pill.
  const offenders: string[] = [];
  for (const [name, map] of Object.entries(VOCABULARY)) {
    for (const [key, label] of Object.entries(map)) {
      if (label.split(/\s+/).length > 5) offenders.push(`${name}.${key}: "${label}"`);
    }
  }
  assert.deepEqual(offenders, []);
});

test("no label carries an em dash", () => {
  // It hides whether a clause explains, qualifies, or restarts, and a label has no room for
  // any of the three.
  const offenders: string[] = [];
  for (const [name, map] of Object.entries(VOCABULARY)) {
    for (const [key, label] of Object.entries(map)) {
      if (label.includes("—")) offenders.push(`${name}.${key}`);
    }
  }
  assert.deepEqual(offenders, []);
});

test("no two maps in the suite disagree about one word", () => {
  // The same label meaning two things is as bad as two labels meaning one. "Unrelated" is
  // the allowed case: it is the same idea on two axes, and each sits under a heading that
  // names its axis.
  // Two entries, each the same idea on a different axis, in tools a reader never sees side
  // by side. "Unrelated" is a relation to a target and a relation to a product; "Not
  // comparable" is a source that cannot be measured against a target and a requirement that
  // cannot be measured across two documents. Naming them differently would be the drift.
  const SHARED_BY_DESIGN = new Set(["Unrelated", "Not comparable", "Could be stronger", "Not met"]);
  const seen = new Map<string, string[]>();
  for (const [name, map] of Object.entries(VOCABULARY)) {
    for (const label of Object.values(map)) {
      if (SHARED_BY_DESIGN.has(label)) continue;
      seen.set(label, [...(seen.get(label) ?? []), name]);
    }
  }
  const collisions = [...seen.entries()]
    .filter(([, maps]) => new Set(maps).size > 1)
    .map(([label, maps]) => `"${label}" in ${[...new Set(maps)].join(", ")}`);
  assert.deepEqual(collisions, []);
});

test("reader-facing copy uses no em dash, in any tool", () => {
  // It hides whether a clause explains, qualifies, or restarts, which is the one thing a
  // reader needs from a connective in a sentence about evidence. The rule covered three
  // Scout files and left eighteen in Expert's and Aligner's help panels, where the prose is
  // longest and the ambiguity costs most.
  //
  // Comments keep theirs: they are for whoever maintains this, not for a reader of a result.
  const files = [
    "components/scout-signal-help.tsx",
    "components/expert-signal-help.tsx",
    "components/aligner-signal-help.tsx",
    "components/inspector-signal-help.tsx",
    "components/evidence-provenance.tsx",
    "components/excluded-measurements.tsx",
    "components/comparator-cohort.tsx",
    "components/expert-coverage-strip.tsx",
  ];
  const offenders: string[] = [];
  for (const file of files) {
    const text = readFileSync(path.resolve(import.meta.dirname, "..", file), "utf8");
    const code = text
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/^\s*\/\/.*$/gm, "");
    // The empty-value placeholder is the one place the glyph is right.
    if (code.replace(/\|\|\s*"—"/g, "").includes("—")) offenders.push(file);
  }
  assert.deepEqual(offenders, [], "rewrite the sentence; the dash is hiding its own job");
});
