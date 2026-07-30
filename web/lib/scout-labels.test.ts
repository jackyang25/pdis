import assert from "node:assert/strict";
import test from "node:test";

import { displayAttributeLabel, sourceDisplayLabel } from "./scout-labels.ts";

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
