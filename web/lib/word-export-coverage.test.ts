/**
 * Every tool's final result exports to Word the same way: the `word` action beside its JSON
 * download, through the one `WordExportButton`. A tool given its own export button, or none,
 * is the drift this pins.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";

const WEB = path.resolve(import.meta.dirname, "..");

for (const tool of ["inspector", "aligner", "screener", "scout", "drafter"] as const) {
  test(`${tool} offers its final result as a Word file beside the JSON`, () => {
    const page = readFileSync(path.join(WEB, "app", tool, "page.tsx"), "utf8");
    const actions = page.slice(page.indexOf("<FinalResultActions"));
    assert.match(actions.slice(0, actions.indexOf("/>")), new RegExp(`word=\\{[\\s\\S]*tool: "${tool}"`));
    assert.doesNotMatch(page, /ExportButton\b/, `${tool} draws its own export button`);
  });
}
