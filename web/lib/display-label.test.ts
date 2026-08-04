/**
 * Guards the one formatter every config selector shares, and the shape of the
 * indication keys it renders.
 *
 * Which indications to offer is an editorial judgment and stays documented in
 * `shared/indications.yaml`. What is mechanically checkable is the shape of a
 * key, and that shape is load-bearing: the picker submits the raw key, and
 * `services/scout/stages/query_extractor.py` joins it verbatim into query text
 * without de-underscoring it. A compound key would search for itself.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";

import { displayLabel } from "./display-label.ts";

const REPO = path.resolve(import.meta.dirname, "..", "..");
const VOCAB = path.join(REPO, "shared", "indications.yaml");

test("single-token keys keep the labels they already had", () => {
  assert.equal(displayLabel("rsv"), "RSV");
  assert.equal(displayLabel("hiv"), "HIV");
  assert.equal(displayLabel("gbs"), "GBS");
  assert.equal(displayLabel("malaria"), "Malaria");
  assert.equal(displayLabel("itpp"), "iTPP");
  assert.equal(displayLabel("ctpp"), "cTPP");
});

test("acronyms resolve per word, not only for a whole key", () => {
  // No shipped key is compound today; `scout-labels.ts` reads the same set per
  // word, and the two disagreeing about one word is what sharing it prevents.
  assert.equal(displayLabel("who_tpp"), "WHO TPP");
  assert.equal(displayLabel("example_org"), "Example Org");
});

test("every shared indication is one lowercase word", () => {
  // Read as text rather than adding a YAML parser to the web package, the same
  // way document-formats.test.ts reads the chunker's declaration.
  const source = readFileSync(VOCAB, "utf8");
  const tags = [...source.matchAll(/^\s+-\s+(\S+)\s*$/gm)].map((match) => match[1]);
  assert.ok(tags.length > 0, "the shared indication vocabulary is empty");
  for (const tag of tags) {
    assert.match(
      tag,
      /^[a-z0-9]+$/,
      `${tag} is not one lowercase word; it reaches retrieval verbatim, so a `
        + `syndrome or population belongs in the document, not in the tag`,
    );
    assert.ok(displayLabel(tag).trim().length > 0, `${tag} renders no label`);
  }
});
