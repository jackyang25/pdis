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

test("every picker names its runs in that tool's own terms", () => {
  // The label is the one thing a shared component cannot know: only the tool
  // knows whether a run is a document, a comparison, a gate, or a query.
  for (const page of pagesThatKeepRuns()) {
    assert.match(
      page.source,
      /label=\{\(value\)/,
      `${page.tool} renders the picker without a label`,
    );
  }
});
