/**
 * Every tool that keeps runs lets you see and remove them.
 *
 * The store was made to hold a list for all six tools at once, but the picker
 * was rendered in two. The other four accumulated runs invisibly — and since
 * the limit refuses a sixth rather than dropping the oldest, a user could reach
 * it with no control anywhere to get back under it.
 */

import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import test from "node:test";

const APP = path.resolve(import.meta.dirname, "..", "app");

/** Pages that record a finished run into the session store. */
function pagesThatKeepRuns(): { tool: string; source: string }[] {
  return readdirSync(APP, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => ({
      tool: entry.name,
      source: (() => {
        try {
          return readFileSync(path.join(APP, entry.name, "page.tsx"), "utf8");
        } catch {
          return "";
        }
      })(),
    }))
    .filter((page) => page.source.includes("addResult("));
}

test("a tool that keeps runs also offers the run picker", () => {
  const pages = pagesThatKeepRuns();
  assert.ok(pages.length >= 5, `expected most tools to keep runs, found ${pages.length}`);
  for (const page of pages) {
    assert.ok(
      page.source.includes("<RunHistory"),
      `${page.tool} records runs but never renders RunHistory, so they cannot be `
        + `switched or removed — and the limit refuses new ones`,
    );
  }
});

test("the picker is always given a way to remove a run", () => {
  // Removing is the only route back under the limit; a picker without it is a
  // dead end rather than a convenience.
  for (const page of pagesThatKeepRuns()) {
    assert.ok(
      page.source.includes("onRemove={removeResult}"),
      `${page.tool} renders the picker without a remove handler`,
    );
  }
});

test("every picker names its runs through the one shared identity", () => {
  // The label is the one thing a shared *component* cannot know — only the tool knows
  // whether a run is a document, a comparison, a gate or a query — but that is an
  // argument for one function per tool, not for a lambda per page.
  //
  // Written as lambdas, two of them drifted from the filename beside them: Expert's
  // picker showed only the gate while its file named the documents, so two runs of one
  // gate on different documents were two identical rows. Neither side could see the
  // other. `runLabel` and `runFilename` now read one `runIdentity`, so a name has one
  // definition and the two forms can differ in punctuation and never in substance.
  for (const page of pagesThatKeepRuns()) {
    assert.match(
      page.source,
      new RegExp(`label=\\{\\(value\\) => runLabel\\(value, "${page.tool}"\\)\\}`),
      `${page.tool} names its runs its own way instead of through runLabel`,
    );
  }
});

test("a tool that exports a file names it from the same identity", () => {
  // The drift this closes ran between the picker and the export, so the test has to look
  // at both. Two spellings, because a download is a prop on one component and a field on
  // another: `filename={…}` and `filename: …`. Either way the value must come from the
  // shared identity rather than be assembled at the call site — Chunker used to build its
  // own out of a template string.
  const naming = /filename[=:]\s*\{?\s*(runFilename\(|\w+ResultFilename\()/;
  const exporting = pagesThatKeepRuns().filter((page) => /filename[=:]/.test(page.source));
  assert.ok(
    exporting.length >= 5,
    `expected most tools to export, found ${exporting.length}`,
  );
  for (const page of exporting) {
    assert.match(
      page.source,
      naming,
      `${page.tool} builds an export name outside the shared identity`,
    );
  }
});
