/**
 * The card renders a reading and decides nothing.
 *
 * A point shows the findings it names from the tool's own list, so these pin what a reader
 * sees in each state: a ready reading, one with nothing to raise, a failure they can retry,
 * and a read still in flight. All four tools render this one component.
 */

import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { loadComponent } from "../test-support/load-component.ts";
import type { PriorityFinding } from "./priorities.ts";

const { PriorityPanel } = loadComponent(
  fileURLToPath(new URL("../components/ui/priority-panel.tsx", import.meta.url)),
);

const findings: PriorityFinding[] = [
  { id: "u-1", subject: "Efficacy", group: "Profile", verdicts: ["Insufficient"], statements: [], quote: "at least 80%", blockIds: [] },
  { id: "u-2", subject: "Safety", group: "Profile", verdicts: ["Specified"], statements: [], blockIds: [] },
];

function render(reading: unknown, list: PriorityFinding[] = findings): string {
  return renderToStaticMarkup(React.createElement(PriorityPanel, { findings: list, reading, defaultOpen: true }));
}

test("a ready reading shows its whole summary and each point with the findings it names", () => {
  const summary = "The opening sentence. ".repeat(40) + "The final qualification must remain reachable.";
  const html = render({
    state: "ready",
    reading: { summary, points: [{ title: "Efficacy is open", statement: "The target is not supported.", finding_ids: ["u-1"] }] },
  });
  assert.match(html, /The final qualification must remain reachable/);
  assert.match(html, /Efficacy is open/);
  assert.match(html, /The target is not supported/);
  // The finding as the tool names it: subject, where it sits, its verdict. The same two lines
  // in every tool, so the document's words are left to the source trigger.
  assert.match(html, /Efficacy/);
  assert.match(html, /Profile · Insufficient/);
  assert.doesNotMatch(html, /at least 80%/);
  // Only the findings the point names.
  assert.doesNotMatch(html, /Safety/);
});

test("the count beside the title is the number of points", () => {
  const html = render({
    state: "ready",
    reading: { summary: "S", points: [
      { title: "One", statement: "A.", finding_ids: ["u-1"] },
      { title: "Two", statement: "B.", finding_ids: ["u-2"] },
    ] },
  });
  assert.match(html, /Priorities<\/span><span class="tabular-nums text-muted-foreground">2<\/span>/);
});

test("a reading with nothing to raise says so rather than showing an empty list", () => {
  const html = render({ state: "ready", reading: { summary: "All units are specified.", points: [] } });
  assert.match(html, /All units are specified/);
  assert.match(html, /Nothing in this result needs attention first/);
});

test("a failure is said quietly, with its reason and a way to ask again", () => {
  const html = render({ state: "failed", reason: "The provider timed out.", retry: () => {} });
  assert.match(html, /No priorities for this run\. The provider timed out\./);
  assert.match(html, /Try again/);
});

test("a read in flight holds the space, and a result with no findings says it has none", () => {
  assert.match(render({ state: "loading" }), /Reading this result/);
  assert.match(render(undefined, []), /This result holds no findings to read/);
});

test("the card says the selection is the AI's and the result below is unchanged", () => {
  const html = render({ state: "ready", reading: { summary: "S", points: [] } });
  assert.match(html, /Read by AI from every finding in this result/);
});
