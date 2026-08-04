/**
 * Binds the queued stage name to the gateway that emits it.
 *
 * Progress display resolves a stage name against the running tool's own step
 * list and falls back to the first step. So if these two strings drift, a run
 * waiting for capacity silently announces that parsing has begun: a wrong
 * label rather than a missing one, which no error surface would catch.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";

import { QUEUED_STAGE } from "./api.ts";

const REPO = path.resolve(import.meta.dirname, "..", "..");
const STREAMING = path.join(REPO, "api", "streaming.py");

test("the queued stage name matches api/streaming.py", () => {
  const source = readFileSync(STREAMING, "utf8");
  const declaration = /^QUEUED_STAGE\s*=\s*["']([^"']+)["']/m.exec(source);
  assert.ok(declaration, "api/streaming.py no longer declares QUEUED_STAGE");
  assert.equal(
    QUEUED_STAGE,
    declaration[1],
    "web/lib/api.ts drifted from api/streaming.py",
  );
});

test("the gateway announces a queue only when a run actually waits", () => {
  const source = readFileSync(STREAMING, "utf8");
  // A blocking acquire without the non-blocking probe would emit the queued
  // stage on every run, changing the event stream of an uncontended one.
  assert.match(
    source,
    /if not _run_slots\.acquire\(blocking=False\)/,
    "the queued stage must be conditional on the cap being spent",
  );
});
