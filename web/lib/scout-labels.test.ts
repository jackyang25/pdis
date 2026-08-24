import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";

import {
  CALIBRATION_BASIS_LABEL,
  DISPOSITION_LABEL,
  GROUNDING_LABEL,
  OUTCOME_LABEL,
  PRECEDENT_LABEL,
  QUERY_TRACK_LABEL,
  RELATIONSHIP_LABEL,
  SEMANTIC_STATUS_LABEL,
  TARGET_ROLE_LABEL,
  displayAttributeLabel,
  sourceDisplayLabel,
} from "./scout-labels.ts";

test("a field ref renders the same however it separates words", () => {
  // The evidence map replaced only underscores while the document trace also
  // replaced dots and hyphens, so one ref rendered two ways across views.
  assert.equal(displayAttributeLabel("vaccine.dose_volume"), "Dose Volume");
  assert.equal(displayAttributeLabel("vaccine.cold-chain_window"), "Cold Chain Window");
  assert.equal(displayAttributeLabel("dose_volume"), "Dose Volume");
});

test("a known acronym stays upper case anywhere in the label", () => {
  assert.equal(displayAttributeLabel("vaccine.fda_alignment"), "FDA Alignment");
  assert.equal(displayAttributeLabel("who_prequalification"), "WHO Prequalification");
});

test("collapsed separators never produce empty words", () => {
  assert.equal(displayAttributeLabel("vaccine.dose__volume"), "Dose Volume");
  assert.equal(displayAttributeLabel("vaccine..dose"), "Dose");
});

test("a source lane prefers its provided label over a derived one", () => {
  assert.equal(
    sourceDisplayLabel("clinicaltrials", { clinicaltrials: "ClinicalTrials.gov" }),
    "ClinicalTrials.gov",
  );
  assert.equal(sourceDisplayLabel("semantic_scholar"), "Semantic Scholar");
});


/**
 * The vocabulary as a whole, not one label at a time.
 *
 * "Numbers not calibrated" was fixed as a one-off, and the same faults were sitting in
 * `coverageLabel` ("Insufficient basis" - basis of what?) and in a second copy of
 * `GROUNDING_LABEL` that had drifted to "Partial" while the fields tab said "Partly
 * grounded". These tests make the rule enforceable instead of remembered.
 */

/** Words that require knowing the tool's internals to read. */
const INTERNAL_VOCABULARY = [
  "calibrat",
  "basis of",
  "claim-compatible",
  "scalar",
  "atomic",
  "disposition",
  "conformity",
  "projection",
  "ledger",
  "semantic slot",
];

const USER_FACING_LABELS: Record<string, Record<string, string>> = {
  RELATIONSHIP_LABEL,
  GROUNDING_LABEL,
  PRECEDENT_LABEL,
  OUTCOME_LABEL,
  DISPOSITION_LABEL,
  SEMANTIC_STATUS_LABEL,
  CALIBRATION_BASIS_LABEL,
  TARGET_ROLE_LABEL,
  QUERY_TRACK_LABEL,
};

test("no label asks the reader to know the tool's internals", () => {
  const offenders: string[] = [];
  for (const [name, map] of Object.entries(USER_FACING_LABELS)) {
    for (const [key, label] of Object.entries(map)) {
      const lowered = label.toLowerCase();
      for (const word of INTERNAL_VOCABULARY) {
        if (lowered.includes(word)) offenders.push(`${name}.${key}: "${label}" (${word})`);
      }
    }
  }
  assert.deepEqual(offenders, []);
});

test("no label is empty, and none repeats another within its own map", () => {
  // A duplicate inside one map means two distinct values render identically, which is a
  // silent merge of two different states.
  for (const [name, map] of Object.entries(USER_FACING_LABELS)) {
    const labels = Object.values(map);
    assert.ok(labels.every((label) => label.trim().length > 0), `${name} has an empty label`);
    assert.equal(new Set(labels).size, labels.length, `${name} renders two values the same`);
  }
});

test("every label is short enough to sit inline beside a value", () => {
  // These are read next to numbers and titles, not as sentences.
  for (const [name, map] of Object.entries(USER_FACING_LABELS)) {
    for (const [key, label] of Object.entries(map)) {
      assert.ok(
        label.split(" ").length <= 5,
        `${name}.${key} is a sentence, not a label: "${label}"`,
      );
    }
  }
});

test("the scout page keeps no second copy of any label vocabulary", () => {
  // Two copies of GROUNDING_LABEL is how one run rendered "Partial" in the evidence map
  // and "Partly grounded" in the fields tab at the same time.
  const page = readFileSync(
    path.resolve(import.meta.dirname, "..", "app", "scout", "page.tsx"),
    "utf8",
  );
  for (const name of Object.keys(USER_FACING_LABELS)) {
    assert.ok(
      !page.includes(`const ${name}`),
      `app/scout/page.tsx defines its own ${name}; import it from lib/scout-labels instead`,
    );
  }
});

test("no view re-types a whole label vocabulary", () => {
  // The test above checks the *name*. Two copies called PRECEDENT_META and OUTCOME_META
  // walked straight past it and drifted anyway - the shared vocabulary said "Unknown"
  // while the copy said "Outcome unknown" - and a relationship filter went on offering
  // four labels it had typed out itself.
  //
  // The whole set, not one word: "Unknown" and "Unrelated" also belong to the projection
  // relationship filter, which is a different axis that happens to share vocabulary, and
  // to a slot placeholder. Flagging those would be wrong. A file that contains every
  // label of one map is not sharing a word, it is holding a copy.
  const files = ["app/scout/page.tsx", "lib/scout-evidence-map.ts", "lib/scout-document-trace.ts"];
  const offenders: string[] = [];
  for (const file of files) {
    const text = readFileSync(path.resolve(import.meta.dirname, "..", file), "utf8");
    for (const [name, map] of Object.entries(USER_FACING_LABELS)) {
      const labels = Object.values(map);
      if (labels.every((label) => text.includes(`"${label}"`) || text.includes(`>${label}<`))) {
        offenders.push(`${file} holds a full copy of ${name}`);
      }
    }
  }
  assert.deepEqual(offenders, []);
});

test("the how-to-read panel names every value it claims to explain", () => {
  // The panel spells the vocabulary out in prose, which is right for the one place that
  // teaches it rather than applies it, and wrong to leave unchecked: its sentence said
  // "Direct, Adjacent, None found, or Unknown" while the chips it explained had stopped
  // saying that.
  const help = readFileSync(
    path.resolve(import.meta.dirname, "..", "components", "scout-signal-help.tsx"),
    "utf8",
  );
  const section = (topic: string) => {
    const start = help.indexOf(`  ${topic}: {`);
    assert.ok(start !== -1, `the panel has no ${topic} topic`);
    return help.slice(start, help.indexOf("promptRef", start));
  };
  // Keyed by the panel's own topic names, so a renamed topic fails loudly here rather
  // than silently checking nothing.
  const cases: [string, Record<string, string>][] = [
    ["relationships", RELATIONSHIP_LABEL],
    ["grounding", GROUNDING_LABEL],
    ["precedent", { ...PRECEDENT_LABEL, ...OUTCOME_LABEL }],
  ];
  const missing: string[] = [];
  for (const [topic, map] of cases) {
    const text = section(topic);
    for (const label of Object.values(map)) {
      if (!text.includes(label)) missing.push(`${topic}: "${label}"`);
    }
  }
  assert.deepEqual(missing, []);
});

test("the docs glossary lists the labels the interface actually renders", () => {
  // It listed enum keys - "contradicts, extends, confirms", "partial", "none" - while the
  // interface rendered "Conflicts, Supports, Adds context", "Partly grounded", "None
  // found". Three drifts in one four-row table, and nothing could notice.
  const knowledge = JSON.parse(
    readFileSync(
      path.resolve(import.meta.dirname, "..", "..", "shared", "product_knowledge.json"),
      "utf8",
    ),
  );
  const axes: { term: string; description: string }[] =
    knowledge.sections.find((section: { id: string }) => section.id === "scout")
      .content.find((block: { title?: string }) => block.title === "Result axes").items;
  const described = (term: string) =>
    axes.find((axis) => axis.term === term)?.description ?? "";
  const cases: [string, Record<string, string>][] = [
    ["Relation to document target", RELATIONSHIP_LABEL],
    ["Grounding", GROUNDING_LABEL],
    ["Precedent", { ...PRECEDENT_LABEL, ...OUTCOME_LABEL }],
  ];
  const missing: string[] = [];
  for (const [term, map] of cases) {
    const text = described(term);
    assert.ok(text, `the glossary has no "${term}" axis`);
    for (const label of Object.values(map)) {
      if (!text.includes(label)) missing.push(`${term}: "${label}"`);
    }
  }
  assert.deepEqual(missing, []);
});

test("the glossary names each axis exactly as the interface heads it", () => {
  // The gap this closes: the glossary said "Relationship" while the section heading said
  // "External evidence", so the one axis had two names and neither test noticed, because one
  // checked the glossary against the label maps and the other checked the tooltip against
  // the heading. Nothing checked the glossary against the heading.
  const knowledge = JSON.parse(
    readFileSync(
      path.resolve(import.meta.dirname, "..", "..", "shared", "product_knowledge.json"),
      "utf8",
    ),
  );
  const page = readFileSync(
    path.resolve(import.meta.dirname, "..", "app", "scout", "page.tsx"),
    "utf8",
  );
  const axes: { term: string }[] =
    knowledge.sections.find((section: { id: string }) => section.id === "scout")
      .content.find((block: { title?: string }) => block.title === "Result axes").items;
  const unrendered = axes
    .map((axis) => axis.term)
    .filter(
      // Two forms, the same two the tooltip test allows: a literal child, or a prop on
      // `SignalVerdict`.
      (term) => !page.includes(`>${term}</SectionLabel>`) && !page.includes(`label="${term}"`),
    );
  assert.deepEqual(unrendered, [], "a glossary axis names something no heading renders");
});

test("each tooltip title matches the heading it explains", () => {
  // They had drifted to "Evidence relationships" and "Evidence · Grounding" while the
  // interface rendered "External evidence" and "Grounding", so opening a tooltip named the
  // thing differently from the heading that opened it.
  const help = readFileSync(
    path.resolve(import.meta.dirname, "..", "components", "scout-signal-help.tsx"),
    "utf8",
  );
  const page = readFileSync(
    path.resolve(import.meta.dirname, "..", "app", "scout", "page.tsx"),
    "utf8",
  );
  const titles = [...help.matchAll(/title:\s*"([^"]+)"/g)].map((match) => match[1]);
  assert.equal(titles.length, 4, "expected four result axes");
  for (const title of titles) {
    // Two forms, because two of the four reach `SectionLabel` as a prop on `SignalVerdict`
    // rather than as literal children.
    assert.ok(
      page.includes(`>${title}</SectionLabel>`) || page.includes(`label="${title}"`),
      `no section heading renders "${title}"`,
    );
  }
});

test("reader-facing Scout copy uses no em dashes", () => {
  // Reserved for the empty-value placeholder, where it is the right glyph. In prose it
  // hides whether a clause explains, qualifies, or restarts the sentence.
  const files = ["components/scout-signal-help.tsx", "components/evidence-provenance.tsx",
    "components/excluded-measurements.tsx"];
  for (const file of files) {
    const text = readFileSync(path.resolve(import.meta.dirname, "..", file), "utf8");
    assert.ok(!text.includes("—"), `${file} contains an em dash`);
  }
  const knowledge = readFileSync(
    path.resolve(import.meta.dirname, "..", "..", "shared", "product_knowledge.json"),
    "utf8",
  );
  assert.ok(!knowledge.includes("—"), "product_knowledge.json contains an em dash");
});

test("the how-to-read panel is the one place the vocabulary and its prompts live", () => {
  // The prompt link rendered only on the inline per-label tooltip, so a tool whose
  // vocabulary lives in one panel had no route to the instructions behind it. Scout no
  // longer has per-heading tooltips at all: four axes are told apart by contrast, and a
  // tooltip on one cannot show how it differs from the other three.
  const help = readFileSync(
    path.resolve(import.meta.dirname, "..", "components", "ui", "signal-help.tsx"),
    "utf8",
  );
  const panel = help.slice(help.indexOf("export function SignalHelp"));
  assert.ok(
    /<SignalTopicBody topic={topic} withPromptLink/.test(panel),
    "SignalHelp no longer passes withPromptLink, so the panel lost the prompt link",
  );
  const page = readFileSync(
    path.resolve(import.meta.dirname, "..", "app", "scout", "page.tsx"),
    "utf8",
  );
  assert.ok(
    !page.includes("ScoutSignalLabel"),
    "Scout reintroduced per-heading tooltips; the panel is the single explanation",
  );
  assert.ok(page.includes("<ScoutSignalHelp />"), "Scout dropped its how-to-read entry point");
});
