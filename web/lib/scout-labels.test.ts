import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";

import {
  CALIBRATION_BASIS_LABEL,
  DISPOSITION_LABEL,
  GROUNDING_LABEL,
  GROUNDING_TONE,
  OUTCOME_LABEL,
  OUTCOME_TONE,
  PRECEDENT_LABEL,
  precedentStatusLabel,
  statementReviewReason,
  TARGET_MAPPING_ISSUE_LABEL,
  verdictNote,
  verdictReason,
  reviewRecommendationReason,
  QUERY_TRACK_LABEL,
  RELATIONSHIP_LABEL,
  RELATIONSHIP_TONE,
  SEMANTIC_STATUS_LABEL,
  sourceIdentityCaveat,
  TARGET_ROLE_LABEL,
  displayAttributeLabel,
  sourceDisplayLabel,
} from "./scout-labels.ts";
import { relationshipLabel } from "./scout-projection-roles.ts";

test("a field ref renders the same however it separates words", () => {
  // The evidence map replaced only underscores while the document trace also
  // replaced dots and hyphens, so one ref rendered two ways across views.
  assert.equal(displayAttributeLabel("vaccine.dose_volume"), "Dose volume");
  assert.equal(displayAttributeLabel("vaccine.cold-chain_window"), "Cold chain window");
  assert.equal(displayAttributeLabel("dose_volume"), "Dose volume");
});

test("a known acronym stays upper case anywhere in the label", () => {
  assert.equal(displayAttributeLabel("vaccine.fda_alignment"), "FDA alignment");
  assert.equal(displayAttributeLabel("who_prequalification"), "WHO prequalification");
});

test("a variable name is a phrase in sentence case, the same in every tool", () => {
  assert.equal(displayAttributeLabel("vaccine.duration_of_protection"), "Duration of protection");
  assert.equal(displayAttributeLabel("vaccine.cogs"), "COGS");
});

test("collapsed separators never produce empty words", () => {
  assert.equal(displayAttributeLabel("vaccine.dose__volume"), "Dose volume");
  assert.equal(displayAttributeLabel("vaccine..dose"), "Dose");
});

test("a source lane prefers its provided label over a derived one", () => {
  assert.equal(
    sourceDisplayLabel("clinicaltrials", { clinicaltrials: "ClinicalTrials.gov" }),
    "ClinicalTrials.gov",
  );
  assert.equal(sourceDisplayLabel("semantic_scholar"), "Semantic Scholar");
});

test("source labels preserve registered names when a saved result has no adapter labels", () => {
  assert.equal(sourceDisplayLabel("pubmed"), "PubMed");
  assert.equal(sourceDisplayLabel("clinicaltrials"), "ClinicalTrials.gov");
  assert.equal(sourceDisplayLabel("fda_safety"), "FDA Safety");
  assert.equal(sourceDisplayLabel("isrctn"), "ISRCTN");
  assert.equal(sourceDisplayLabel("ctis"), "CTIS");
  assert.equal(sourceDisplayLabel("europepmc"), "Europe PMC");
  assert.equal(sourceDisplayLabel("who_guidelines"), "WHO Guidelines");
  assert.equal(sourceDisplayLabel("pubmed", { pubmed: "Adapter label" }), "Adapter label");
  assert.equal(sourceDisplayLabel("new_source"), "New Source");
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
  assert.equal(titles.length, 5, "expected five result axes");
  for (const title of titles) {
    // Three forms. Two of the field axes reach `SectionLabel` as a prop on `SignalVerdict`
    // rather than as literal children. The fifth, the relation a record has to the uploaded
    // product, is headed by a filter rather than by a section - the records tabs have no
    // heading over that axis - so the filter's accessible name is what must match. The rule
    // is unchanged: a tooltip's title has to be words the reader can already see.
    assert.ok(
      page.includes(`>${title}</SectionLabel>`)
        || page.includes(`label="${title}"`),
      `nothing on screen renders "${title}"`,
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
  assert.ok(page.includes("<ScoutSignalHelp"), "Scout dropped its how-to-read entry point");
});

test("a tool that publishes a vocabulary explains it in one panel, not per row", () => {
  // Scout settled this and Inspector had not: it carried a help icon on every status pill
  // and every finding reason as well as a panel, which is 32 units times two affordances
  // glossing three sentences. The argument is the same in both tools - an icon on one
  // value cannot show how it differs from the values it is not, and telling them apart is
  // the thing a reader actually gets wrong.
  const tools = [
    { page: ["app", "scout", "page.tsx"], label: "ScoutSignalLabel", help: "<ScoutSignalHelp" },
    { page: ["app", "inspector", "page.tsx"], label: "InspectorSignalLabel", help: "<InspectorSignalHelp" },
  ];
  for (const tool of tools) {
    const source = readFileSync(path.resolve(import.meta.dirname, "..", ...tool.page), "utf8");
    assert.ok(
      !source.includes(tool.label),
      `${tool.page[1]} reintroduced per-row tooltips; the panel is the single explanation`,
    );
    assert.ok(
      source.includes(tool.help),
      `${tool.page[1]} has no how-to-read entry point, so the vocabulary is explained nowhere`,
    );
  }
});

test("how a source was matched is said in one place, and only where it matters", () => {
  // The caveat lived as a string built inside the plot, so the same measurement carried it on
  // a chart point and not in the Comparators panel, which is where a reader audits the cohort.
  // It is load-bearing: `calibrationStatus` cannot report a verified basis unless every
  // admitted measurement is canonical, so this is what caps a cohort at "Limited".
  assert.equal(sourceIdentityCaveat("canonical"), "", "a matched record needs no caveat");
  // Retired: Scout no longer matches a source by its title, so a saved status of that
  // name is unknown here and invents no caveat.
  assert.equal(sourceIdentityCaveat("title_fallback"), "");
  assert.equal(sourceIdentityCaveat("url_fallback"), "Matched by link only");
  assert.equal(sourceIdentityCaveat("anything_else"), "", "an unknown status invents no caveat");

  const read = (file: string) =>
    readFileSync(path.resolve(import.meta.dirname, "..", file), "utf8");
  for (const file of [
    "components/comparator-distribution-plot.tsx",
    "components/comparator-cohort.tsx",
  ]) {
    assert.match(read(file), /sourceIdentityCaveat/, `${file} does not show how a source matched`);
    assert.ok(
      !/Identified by \$\{/.test(read(file)),
      `${file} builds the caveat itself again`,
    );
  }

  // Not in the excluded panel: identity never decides admission, so on a measurement already
  // outside the cohort it would be a caveat about nothing.
  assert.ok(
    !read("components/excluded-measurements.tsx").includes("sourceIdentityCaveat"),
    "the excluded panel caveats a measurement that is not in the cohort",
  );
});

test("a toolbar explains the axis it filters on, not the other one", () => {
  // Scout has two relationship vocabularies and `models.py` names the trap at the
  // vocabulary itself: a field's relation to a target (Conflicts, Supports, Adds context,
  // Unrelated) and a record's relation to the uploaded product (Direct, Analogous,
  // Adjacent, Unrelated). They share the token `unrelated` and mean different things by
  // it. The how-to-read panel used to show all of Scout's topics wherever it appeared, so
  // a reader filtering records opened it and read the other axis's definition of the word
  // in front of them.
  const page = readFileSync(
    path.resolve(import.meta.dirname, "..", "app", "scout", "page.tsx"),
    "utf8",
  );
  const toolbar = page.slice(page.indexOf("function ProjectionToolbar"));
  const scope = toolbar.match(/<ScoutSignalHelp\s+only=\{\[([^\]]*)\]\}/);
  assert.ok(scope, "the records toolbar explains every Scout topic, not the one it filters on");
  assert.equal(
    scope[1].replace(/\s/g, ""),
    '"targetRelationship"',
    "the records toolbar explains an axis it does not filter on",
  );
});

test("the glossary and the tooltips list the same axes", () => {
  // Two statements of one vocabulary. The docs page renders the tooltip topics directly -
  // imported, not restated - but `shared/product_knowledge.json` carries its own "Result
  // axes" list, and that one is what the Ask assistant reads. A fifth axis was added to
  // the tooltips and the glossary kept describing four, so the interface explained
  // something the knowledge base had never heard of.
  //
  // Existing checks bound the glossary to the interface and the tooltips to the
  // interface. Nothing bound the two explanations to each other.
  const help = readFileSync(
    path.resolve(import.meta.dirname, "..", "components", "scout-signal-help.tsx"),
    "utf8",
  );
  const titles = [...help.matchAll(/title:\s*"([^"]+)"/g)].map((match) => match[1]);
  const knowledge = JSON.parse(
    readFileSync(path.resolve(import.meta.dirname, "..", "..", "shared", "product_knowledge.json"), "utf8"),
  ) as { sections: { id: string; content: { title?: string; items?: { term: string }[] }[] }[] };
  const axes = knowledge.sections
    .find((section) => section.id === "scout")!
    .content.find((block) => block.title === "Result axes")!
    .items!.map((item) => item.term);
  assert.deepEqual(
    [...axes].sort(),
    [...titles].sort(),
    "the glossary and the tooltips disagree about which axes Scout has",
  );
});

test("a stage that obtained no verdict reads as not assessed, never as a reading", () => {
  // `not_assessed` is recorded by code when a model call failed. Shown as "Unrelated",
  // "Grounding unknown" or "Outcome unknown" it would say the evidence was read and was
  // silent, which is the one thing nobody observed. Neutral, because it is no signal.
  const labels: [string, string][] = [
    [RELATIONSHIP_LABEL.not_assessed, "Not assessed"],
    [GROUNDING_LABEL.not_assessed, "Grounding not assessed"],
    [PRECEDENT_LABEL.not_assessed, "Precedent not assessed"],
    [OUTCOME_LABEL.not_assessed, "Outcome not assessed"],
    [relationshipLabel("not_assessed"), "Product relation not assessed"],
  ];
  for (const [actual, expected] of labels) assert.equal(actual, expected);
  assert.equal(RELATIONSHIP_TONE.not_assessed, "neutral");
  assert.equal(GROUNDING_TONE.not_assessed, "neutral");
  assert.equal(OUTCOME_TONE.not_assessed, "neutral");
});

test("a precedent that was not assessed is named once, not once per axis", () => {
  // One classification decides both axes, so a failure leaves both `not_assessed`.
  // "Precedent not assessed · Outcome not assessed" says one fact twice.
  assert.equal(
    precedentStatusLabel({ precedent: "not_assessed", outcome: "not_assessed" }),
    "Precedent not assessed",
  );
  assert.equal(
    precedentStatusLabel({ precedent: "direct", outcome: "mixed" }),
    "Direct precedent · Mixed outcome",
  );
});

test("an unassessed check shows no reason, because its reason is the pipeline's diagnostic", () => {
  // Code wrote it, so it must not be set where a model's sentence goes.
  assert.equal(verdictReason("not_assessed", "OpenAI request failed: timeout"), "");
  assert.equal(verdictReason("thin", "Two small studies."), "Two small studies.");
});

test("an unresolved statement is explained from its codes, never from its reason's wording", () => {
  // The page once matched phrases and a bracketed token out of `reason`, so rewording the
  // backend's sentence silently changed what a reviewer was told.
  const base = { reason: "Target mapping rejected.", classification: "mapping_failed" as const };
  assert.equal(
    statementReviewReason({ ...base, failure_code: "invalid_target_mapping", issue_codes: ["invalid_target_quote", "missing_field_links"] }),
    "Scout could not create a complete, source-verifiable target from this statement. It remains outside retrieval and statistics. "
      + `Failed checks: ${TARGET_MAPPING_ISSUE_LABEL.invalid_target_quote}; ${TARGET_MAPPING_ISSUE_LABEL.missing_field_links}.`,
  );
  assert.match(
    statementReviewReason({ ...base, classification: "partial_target", failure_code: "invalid_target_mapping", issue_codes: ["duplicate_atomic_target"] }),
    /^Validated targets from this passage were kept\./,
  );
  assert.match(
    statementReviewReason({ ...base, failure_code: "invalid_model_response", issue_codes: [] }),
    /one reliable review decision/,
  );
  // The wording a backend sentence happens to use decides nothing.
  assert.equal(
    statementReviewReason({ reason: "Target mapping rejected [invalid_target_quote].", classification: "uncertain", failure_code: "", issue_codes: [] }),
    "Target mapping rejected [invalid_target_quote].",
  );
});

test("every structural check has a reader's label", () => {
  for (const label of Object.values(TARGET_MAPPING_ISSUE_LABEL)) {
    assert.ok(label.trim() && !label.includes("_"), `"${label}" is not a reader's label`);
  }
});

test("no evidence is the interface's own sentence, neutral on every axis", () => {
  // Set by code when nothing retrieved reached a field: no model call and an empty reason.
  // Neither a failure (`not_assessed`) nor the model's `unknown`, so it is named apart from
  // both and never coloured as a finding.
  for (const [name, map] of [["grounding", GROUNDING_LABEL], ["precedent", PRECEDENT_LABEL], ["outcome", OUTCOME_LABEL]] as const) {
    assert.ok(map.no_evidence, `${name} has no label for no_evidence`);
    assert.notEqual(map.no_evidence, map.unknown);
    assert.notEqual(map.no_evidence, map.not_assessed);
  }
  assert.equal(GROUNDING_TONE.no_evidence, "neutral");
  assert.equal(OUTCOME_TONE.no_evidence, "neutral");
  // Named once, like a failure: one absence on both axes is one fact.
  assert.equal(precedentStatusLabel({ precedent: "no_evidence", outcome: "no_evidence" }), PRECEDENT_LABEL.no_evidence);
  // The note is what the interface says in place of a reason; a verdict has none.
  assert.ok(verdictNote("no_evidence"));
  assert.equal(verdictNote("unknown"), "");
  assert.equal(verdictNote("not_assessed"), "");
  assert.equal(verdictReason("no_evidence", ""), "");
});

test("not searched is the reviewer's choice, neutral and named once", () => {
  // Set by code for a field left out at review: no search ran, so it is neither evidence
  // being absent (`no_evidence`) nor a check failing (`not_assessed`).
  for (const [name, map] of [["grounding", GROUNDING_LABEL], ["precedent", PRECEDENT_LABEL], ["outcome", OUTCOME_LABEL]] as const) {
    assert.ok(map.not_searched, `${name} has no label for not_searched`);
    assert.notEqual(map.not_searched, map.no_evidence);
    assert.notEqual(map.not_searched, map.not_assessed);
  }
  assert.equal(GROUNDING_TONE.not_searched, "neutral");
  assert.equal(OUTCOME_TONE.not_searched, "neutral");
  assert.equal(precedentStatusLabel({ precedent: "not_searched", outcome: "not_searched" }), PRECEDENT_LABEL.not_searched);
  assert.match(verdictNote("not_searched"), /excluded at review/i);
  assert.equal(verdictReason("not_searched", "anything"), "");
});

test("an unavailable review is explained from its code, never from the failure's message", () => {
  // The recorded reason on an unavailable review is the exception the call raised - a
  // diagnostic, not a reviewer's sentence - so the page words it from the code.
  const unavailable = reviewRecommendationReason({
    ai_recommendation: "unavailable", ai_review_failure_code: "response_truncated",
    ai_review_reason: "ModelResponseError: max_output_tokens",
  });
  assert.ok(unavailable);
  assert.doesNotMatch(unavailable, /ModelResponseError|max_output_tokens/);
  for (const code of ["response_truncated", "response_refused", "invalid_model_response", "provider_error"] as const) {
    assert.notEqual(
      reviewRecommendationReason({ ai_recommendation: "unavailable", ai_review_failure_code: code, ai_review_reason: "" }),
      "",
      `${code} has no explanation`,
    );
  }
  assert.equal(
    reviewRecommendationReason({ ai_recommendation: "admit", ai_review_failure_code: "", ai_review_reason: "Comparable cohort." }),
    "Comparable cohort.",
  );
});
