import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";

import { SEARCH_FIELD_LABEL, SEARCH_TEXT_FIELDS } from "./search-fields.ts";

const REPO = path.resolve(import.meta.dirname, "..", "..");

test("the browser's search fields are Searcher's", () => {
  // Searcher owns what a search accepts; the API request and the Assistant's offer are built
  // from the same list, so this copy is the only one that could drift.
  const pipeline = readFileSync(path.join(REPO, "services/searcher/pipeline.py"), "utf8");
  const declared = pipeline.match(/SEARCH_TEXT_FIELDS[^=]*= \{([\s\S]*?)\n\}/)?.[1];
  assert.ok(declared, "SEARCH_TEXT_FIELDS is no longer a dict in services/searcher/pipeline.py");
  assert.deepEqual([...declared.matchAll(/^ {4}"([a-z_]+)":/gm)].map((match) => match[1]), [...SEARCH_TEXT_FIELDS]);
});

test("Searcher's form labels each field from the one list", () => {
  const page = readFileSync(path.join(REPO, "web/app/searcher/page.tsx"), "utf8");
  for (const name of SEARCH_TEXT_FIELDS) {
    assert.ok(page.includes(`SEARCH_FIELD_LABEL.${name}`), `the form does not label ${name} from SEARCH_FIELD_LABEL`);
  }
  // A label typed into the form again could disagree with the one a suggestion shows.
  for (const label of Object.values(SEARCH_FIELD_LABEL)) {
    assert.doesNotMatch(page, new RegExp(`label="${label}`), `"${label}" is typed into the form`);
  }
});
