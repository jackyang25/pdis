/**
 * Every reference in an answer is a markdown link; the scheme says what it is.
 *
 * The alternative was hunting for block IDs in prose, which would have to guess
 * at intent and would turn any lookalike into a control that opens nothing.
 * These pin the two ends: a declared citation is recognised, and anything else
 * stays text rather than becoming a broken control.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";

import { parseCitation } from "./citation.ts";

const REPO = path.resolve(import.meta.dirname, "..", "..");
const AGENT = path.join(REPO, "services", "assistant", "agent.py");

test("the scheme matches the one the agent is told to write", () => {
  const prompt = readFileSync(AGENT, "utf8");
  assert.match(
    prompt,
    /\(block:EXACT-BLOCK-ID\)/,
    "agent.py no longer instructs the block: scheme this file parses",
  );
});

test("a cited passage is recognised", () => {
  assert.deepEqual(parseCitation("block:document/b-0012"), {
    kind: "block",
    blockId: "document/b-0012",
  });
});

test("an evidence link stays an external link", () => {
  assert.deepEqual(parseCitation("https://example.org/paper"), {
    kind: "external",
    href: "https://example.org/paper",
  });
});

test("a scheme citing nothing is text, not an empty control", () => {
  assert.deepEqual(parseCitation("block:"), { kind: "plain" });
  assert.deepEqual(parseCitation("block:   "), { kind: "plain" });
});

test("an unknown scheme degrades to text rather than breaking", () => {
  // What makes adding a kind later safe: until it is handled it is simply not
  // special, and nothing renders wrong in the meantime.
  assert.deepEqual(parseCitation("path:matches[3]"), { kind: "plain" });
  assert.deepEqual(parseCitation("javascript:alert(1)"), { kind: "plain" });
  assert.deepEqual(parseCitation(undefined), { kind: "plain" });
});

test("only http and https are followed", () => {
  // A link is opened in a new tab, so anything that is not a web address is
  // not made clickable at all.
  assert.equal(parseCitation("ftp://example.org/x").kind, "plain");
  assert.equal(parseCitation("//example.org").kind, "plain");
});
