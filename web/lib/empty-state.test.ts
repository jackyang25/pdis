/**
 * "Nothing here" is three different answers, and they had four boxes.
 *
 * Inspector, Archivist, the imported-result popover and Scout each grew their own, varying
 * on three axes at once - dashed or solid border, one line or a heading with a body, an
 * icon or none - none of which marked a difference in what they said. Meanwhile the shared
 * component existed and had a single caller.
 *
 * What matters is the distinction the icons carry: a check that ran and found nothing is
 * good news, a check that did not finish is a question still open, and neither is the same
 * as nothing having been produced yet. A reader who cannot tell them apart cannot tell a
 * clean document from an unread one.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";

const REPO = path.resolve(import.meta.dirname, "..");
const COMPONENT = readFileSync(path.join(REPO, "components", "empty-state.tsx"), "utf8");

/** Files that legitimately say "there is nothing here". */
const SURFACES = [
  path.join("app", "inspector", "page.tsx"),
  path.join("app", "archivist", "page.tsx"),
  path.join("app", "scout", "page.tsx"),
  path.join("components", "document-source-trace.tsx"),
];

test("the three answers are named for the question, not for a colour", () => {
  // `success` and `warning` describe how it looks; a caller choosing between them is
  // choosing a tint. These name what the reader is being told.
  assert.match(COMPONENT, /"absence" \| "clear" \| "unknown"/);
});

test("only a completed check earns a tick", () => {
  // The distinction the whole component exists for. A tick on an unbuilt corpus would
  // claim a search that never ran.
  assert.match(COMPONENT, /clear: CheckCircle2/);
  assert.match(COMPONENT, /unknown: AlertTriangle/);
  assert.match(COMPONENT, /tone === "absence" \? null/, "an absence is claiming an icon");
});

test("an absence is dashed and a stated result is not", () => {
  // The same distinction again in the border: a dashed box reads as a slot waiting to be
  // filled, and "we checked and found nothing" is not a slot.
  assert.match(COMPONENT, /tone === "absence"\s*\n?\s*\? "border border-dashed/);
});

test("no surface hand-rolls its own empty box", () => {
  // The drift this replaces. Four boxes for one idea, and the component meant to be shared
  // had one caller.
  const offenders: string[] = [];
  for (const relative of SURFACES) {
    const source = readFileSync(path.join(REPO, relative), "utf8");
    if (!source.includes("EmptyState")) {
      offenders.push(`${relative} says nothing is there without the shared component`);
    }
  }
  assert.deepEqual(offenders, []);
});

test("Inspector reports its two consistency answers through it", () => {
  // Inspector is where the two answers are furthest apart: findings.length === 0 means
  // either "clean" or "we could not tell", and the status is the only thing that says
  // which.
  const page = readFileSync(path.join(REPO, "app", "inspector", "page.tsx"), "utf8");
  assert.match(page, /tone=\{complete \? "clear" : "unknown"\}/);
  assert.ok(
    !page.includes("CheckCircle2"),
    "Inspector kept its own icons beside the shared component",
  );
});
