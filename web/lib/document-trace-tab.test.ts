/**
 * Four tools trace a result back to the passages it read. The tab is the same tab.
 *
 * Screener's carried a band of prose above the viewer that the other three did not have,
 * and both halves of it were already on the page. The first restated the split between
 * answers cited to a passage and answers read from attached context, which the Answered
 * row prints beside its own count. The second was a per-document tally - "iTPP answered
 * 14 · cTPP answered 7" - which `DocumentTraceViewer` prints live beside the document it
 * is currently showing, one document at a time. Printing both at once meant the sentence
 * had to end by asking the reader not to add them, a caution that existed only because
 * the numbers did.
 *
 * The rule this pins is not "no prose" for its own sake. It is that the viewer owns the
 * trace's own framing - its title, its live connection count, its document and layer
 * selectors - so anything written above it is either a second copy of that or a fact
 * belonging to the view it came from.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";

const WEB = path.resolve(import.meta.dirname, "..");
const TOOLS = ["inspector", "aligner", "scout", "screener"] as const;

/** One tool's trace tab, comments stripped: every rule here is described in one. */
function traceTab(tool: string): string {
  const source = readFileSync(path.join(WEB, "app", tool, "page.tsx"), "utf8")
    .replace(/\{\/\*[\s\S]*?\*\/\}/g, "")
    .replace(/\/\*[\s\S]*?\*\//g, "");
  const start = source.indexOf('<TabsContent value="trace"');
  assert.notEqual(start, -1, `${tool} has no trace tab`);
  const end = source.indexOf("</TabsContent>", start);
  assert.notEqual(end, -1, `${tool}'s trace tab does not close`);
  return source.slice(start, end);
}

test("every tool's trace tab holds the viewer and nothing else", () => {
  for (const tool of TOOLS) {
    const tab = traceTab(tool);
    assert.match(
      tab,
      /<\w+DocumentTrace\b/,
      `${tool}'s trace tab does not render a trace component`,
    );
    for (const shape of [/<p\b/, /<div\b/, /<span\b/]) {
      assert.ok(
        !shape.test(tab),
        `${tool}'s trace tab wraps or annotates the viewer. The viewer states its own `
          + `title, count and selectors; a band above it is a second copy of one of those, `
          + `or a fact that belongs to the view it came from.`,
      );
    }
  }
});

test("the trace tab is spelled the same way in every tool", () => {
  for (const tool of TOOLS) {
    assert.match(
      traceTab(tool),
      /^<TabsContent value="trace" className="m-0">/,
      `${tool} spells the tab differently`,
    );
  }
});

test("one tool's per-document count is the viewer's to state", () => {
  // `answersPerDocument` existed for that removed paragraph and had no other caller.
  const lib = readFileSync(path.join(WEB, "lib/screener-document-trace.ts"), "utf8");
  assert.ok(
    !/answersPerDocument/.test(lib),
    "a per-document tally is being computed again alongside the viewer's live count",
  );
  const viewer = readFileSync(path.join(WEB, "components/document-trace-viewer.tsx"), "utf8");
  assert.match(viewer, /visibleAnnotations\.length/, "the viewer no longer states its own count");
});
