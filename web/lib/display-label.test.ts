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

/** Every declared tag, read as text so the web package needs no YAML parser. */
function indicationTags(source: string): string[] {
  return [...source.matchAll(/^\s+-\s+(\S+)\s*$/gm)].map((match) => match[1]);
}

test("single-token keys keep the labels they already had", () => {
  assert.equal(displayLabel("rsv"), "RSV");
  assert.equal(displayLabel("hiv"), "HIV");
  assert.equal(displayLabel("malaria"), "Malaria");
  assert.equal(displayLabel("itpp"), "iTPP");
  assert.equal(displayLabel("ctpp"), "cTPP");
});

test("no shipped indication renders as an abbreviation of itself", () => {
  /**
   * The label is the one place a reader can notice that a tag is not what they
   * expected — seeing "TB" is what surfaced that queries were searching `tb` rather
   * than tuberculosis. So a tag must never render as an abbreviation the tag itself
   * does not contain: `tb` displayed "TB" while searching "tb", which reads as though
   * the system knew the full name.
   */
  const tags = indicationTags(readFileSync(VOCAB, "utf8"));
  assert.ok(tags.length > 5, "read no indication tags");
  for (const tag of tags) {
    const label = displayLabel(tag);
    assert.equal(
      label.replace(/\s+/g, "").toLowerCase(),
      tag.replace(/_/g, ""),
      `${tag} renders as "${label}", which is not the same word`,
    );
  }
});

test("acronyms resolve per word, not only for a whole key", () => {
  // No shipped key is compound today; `scout-labels.ts` reads the same set per
  // word, and the two disagreeing about one word is what sharing it prevents.
  assert.equal(displayLabel("who_tpp"), "WHO TPP");
  assert.equal(displayLabel("example_org"), "Example Org");
});

test("every shared indication is lowercase words joined by underscores", () => {
  // Read as text rather than adding a YAML parser to the web package, the same way
  // document-formats.test.ts reads the chunker's declaration.
  //
  // Underscores are now permitted, where they were not: `shared.vocabulary.search_term`
  // de-underscores the tag once, upstream, before it becomes query or prompt text. The
  // single-word rule existed because nothing did, and it is what forced Group B
  // Streptococcus to be spelled `gbs` — an abbreviation that also means Guillain-Barre
  // Syndrome, so a vaccine safety search could return the wrong one.
  const source = readFileSync(VOCAB, "utf8");
  const tags = indicationTags(source);
  assert.ok(tags.length > 0, "the shared indication vocabulary is empty");
  for (const tag of tags) {
    assert.match(
      tag,
      /^[a-z0-9]+(_[a-z0-9]+)*$/,
      `${tag} is not lowercase words joined by underscores; a syndrome or population `
        + `belongs in the document, not in the tag`,
    );
    assert.ok(displayLabel(tag).trim().length > 0, `${tag} renders no label`);
  }
});
