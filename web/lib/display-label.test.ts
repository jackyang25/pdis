/**
 * Guards the one formatter every config selector shares.
 *
 * The granularity of an indication tag is a judgment and stays documented in
 * `shared/indications.yaml`; a keyword check here would only restate it badly.
 * What is checkable is mechanical: a tag must be a lowercase key the formatter
 * can render, and rendering must resolve acronyms per word rather than only for
 * a whole key.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";

import { displayLabel } from "./display-label.ts";

const REPO = path.resolve(import.meta.dirname, "..", "..");
const VOCAB = path.join(REPO, "shared", "indications.yaml");

test("acronyms resolve inside a compound key, not only as a whole key", () => {
  assert.equal(displayLabel("gbs_neonatal_sepsis"), "GBS Neonatal Sepsis");
  assert.equal(displayLabel("klebsiella_neonatal_sepsis"), "Klebsiella Neonatal Sepsis");
  assert.equal(displayLabel("pneumococcal_pneumonia"), "Pneumococcal Pneumonia");
});

test("single-token keys keep the labels they already had", () => {
  assert.equal(displayLabel("rsv"), "RSV");
  assert.equal(displayLabel("hiv"), "HIV");
  assert.equal(displayLabel("covid19"), "COVID19");
  assert.equal(displayLabel("malaria"), "Malaria");
  assert.equal(displayLabel("itpp"), "iTPP");
  assert.equal(displayLabel("ctpp"), "cTPP");
});

test("every shared indication is a renderable key", () => {
  // Read as text rather than adding a YAML parser to the web package, the same
  // way document-formats.test.ts reads the chunker's declaration.
  const source = readFileSync(VOCAB, "utf8");
  const tags = [...source.matchAll(/^\s+-\s+(\S+)\s*$/gm)].map((match) => match[1]);
  assert.ok(tags.length > 0, "the shared indication vocabulary is empty");
  for (const tag of tags) {
    assert.match(tag, /^[a-z0-9_]+$/, `${tag} is not a lowercase storage key`);
    const label = displayLabel(tag);
    assert.ok(label.trim().length > 0, `${tag} renders no label`);
    assert.ok(!label.includes("_"), `${tag} renders an unsplit separator`);
  }
});
