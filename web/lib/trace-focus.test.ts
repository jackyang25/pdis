/**
 * Opening a passage in the document trace, and on which layer.
 *
 * The reported behaviour: clicking one finding's "In document" and landing on "All result
 * layers". The passage was cited by six findings across two reasons, and only the block ID
 * reached the viewer — the finding the reader had actually clicked was dropped one function
 * after the click, so the viewer could only ask what was on the block and was right to show
 * everything.
 *
 * These pin the shape that carries the answer. The layer selection itself lives in
 * `document-trace-viewer.tsx` and needs a rendered document; what is checkable here is that
 * a request can name a result, that it does not have to, and that the four tools ask the
 * same way.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";

import { inspectorAnnotationId } from "./inspector-document-trace.ts";
import type { TraceFocus } from "./trace-focus.ts";

const REPO = path.resolve(import.meta.dirname, "..");

test("a request can name the result that sent it", () => {
  const focus: TraceFocus = { blockId: "doc/b-0012", annotationId: "inspector:f-3" };
  assert.equal(focus.annotationId, "inspector:f-3");
});

test("a request does not have to name one", () => {
  // A section card and a coverage cell name a passage and no result. Requiring an
  // annotation would make them invent one, and an invented ID selects the wrong layer
  // rather than falling back to all of them.
  const focus: TraceFocus = { blockId: "doc/b-0012" };
  assert.equal(focus.annotationId, undefined);
});

test("a finding's annotation ID is built in one place", () => {
  // The trigger and the annotation have to spell it identically. Two spellings means the
  // lookup misses, and a miss is silent: it falls back to every layer, which is exactly
  // the bug this fixes wearing the same clothes.
  assert.equal(inspectorAnnotationId("f-3"), "inspector:f-3");
  const built = readFileSync(path.join(REPO, "lib", "inspector-document-trace.ts"), "utf8");
  assert.match(built, /id: inspectorAnnotationId\(item\.id\)/);
  const page = readFileSync(path.join(REPO, "app", "inspector", "page.tsx"), "utf8");
  // Every finding-scoped trigger, not merely one. Asserting a single match let one of the
  // two be deleted with the suite still green - found by deleting it.
  const triggers = page.match(/blockIds=\{item\.cited_block_ids\}/g) ?? [];
  const named = page.match(/annotationId=\{inspectorAnnotationId\(item\.id\)\}/g) ?? [];
  assert.ok(triggers.length > 0, "no finding-scoped trace triggers found");
  assert.equal(
    named.length,
    triggers.length,
    `${triggers.length} triggers but ${named.length} name their assessment: `
      + "one opens on every layer the passage carries",
  );
});

test("every tool asks for a passage the same way", () => {
  // Four pages each held the same useState and the same two callbacks, identical down to
  // the tab they switch to. That is how the annotation half would have been added to three
  // of them and forgotten in the fourth.
  for (const tool of ["scout", "inspector", "aligner", "expert"]) {
    const page = readFileSync(path.join(REPO, "app", tool, "page.tsx"), "utf8");
    assert.match(page, /useTraceFocus\(/, `${tool} hand-rolls its trace focus state`);
    assert.ok(
      !page.includes("traceFocusBlockId"),
      `${tool} kept its own focus state beside the shared hook`,
    );
  }
});

test("the viewer takes one focus value, not two parallel props", () => {
  // The reason the pair became a value: adding `annotationId` beside `focusBlockId` would
  // have been four more props threaded through four adapters that already forward two.
  const viewer = readFileSync(path.join(REPO, "components", "document-trace-viewer.tsx"), "utf8");
  assert.match(viewer, /focus\?: TraceFocus \| null;/);
  assert.ok(
    !viewer.includes("focusBlockId"),
    "the viewer still takes a bare block ID beside the focus value",
  );
});

test("the requested layer is preferred over the block's other results", () => {
  // The fix itself, read from the source: a named annotation decides the layer, and only
  // an unnamed request falls back to what else is on the block.
  const viewer = readFileSync(path.join(REPO, "components", "document-trace-viewer.tsx"), "utf8");
  assert.match(viewer, /focus\?\.annotationId/, "the requested annotation is never consulted");
  assert.match(
    viewer,
    /requested\s*\?\s*\[requested\]/,
    "a named request no longer takes precedence over the block's other annotations",
  );
});
