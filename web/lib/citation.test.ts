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

import { parseCitation, transformCitationUrl } from "./citation.ts";

const REPO = path.resolve(import.meta.dirname, "..", "..");
const AGENT = path.join(REPO, "services", "assistant", "agent.py");

test("the scheme matches the one the agent is told to write", () => {
  const prompt = readFileSync(AGENT, "utf8");
  assert.match(
    prompt,
    /\(<block:EXACT-BLOCK-ID>\)/,
    "agent.py no longer instructs the block: scheme this file parses",
  );
});

test("the agent is told to bracket the destination", () => {
  // A block ID carries the document name, and a name with spaces is not a valid
  // link destination unbracketed: markdown renders the raw syntax as text, which
  // is exactly what a reader saw. Brackets are stripped before the href reaches
  // parseCitation, so nothing downstream changes.
  const prompt = readFileSync(AGENT, "utf8");
  assert.match(prompt, /in angle brackets, never shortened/);
});

test("there are two citation kinds, both openable", () => {
  // A third kind printed a raw JSON path at the reader. Every citation now
  // resolves to something clickable, or it is not a citation.
  const prompt = readFileSync(AGENT, "utf8");
  assert.match(prompt, /Never print a result path/);
});

test("the label and the destination are told apart", () => {
  // Why the destination broke: repeating a full block ID through a table is
  // unreadable, so the model shortened both. A link already separates the two,
  // and saying so lets it keep the answer readable without breaking the target.
  const prompt = readFileSync(AGENT, "utf8");
  assert.match(prompt, /visible text is for the reader/);
  assert.match(prompt, /destination is what opens/);
});

test("a bracketed destination arrives here already unwrapped", () => {
  // remark strips the brackets, so the parser sees the same href either way.
  assert.deepEqual(parseCitation("block:DRAFT AIV iTPP v1 13July2016/b-0080"), {
    kind: "block",
    blockId: "DRAFT AIV iTPP v1 13July2016/b-0080",
  });
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

test("the block scheme survives the renderer's URL sanitiser", () => {
  // The failure every other layer hid: react-markdown blanks any scheme outside
  // http/https/mailto/tel, so `block:` arrived as "" and parseCitation correctly
  // saw nothing to open. API, bundle, parser and resolver all checked out alone.
  assert.equal(
    transformCitationUrl("block:DRAFT AIV iTPP v1 13July2016/b-0010"),
    "block:DRAFT AIV iTPP v1 13July2016/b-0010",
  );
});

test("ordinary links still pass", () => {
  assert.equal(
    transformCitationUrl("https://example.org/paper"),
    "https://example.org/paper",
  );
});

test("the sanitiser is extended, not replaced", () => {
  // The reason it exists: model output must not be able to smuggle a script URL.
  assert.equal(transformCitationUrl("javascript:alert(1)"), "");
  assert.equal(transformCitationUrl("data:text/html,<script>"), "");
  assert.equal(transformCitationUrl("vbscript:msgbox"), "");
});

test("a percent-encoded block id is decoded back to the real one", () => {
  // What the renderer actually delivers: it encodes spaces, and a block ID
  // carries the document name. Undecoded, this matched no block and every
  // citation fell back to plain text while each layer tested green alone.
  assert.deepEqual(
    parseCitation("block:DRAFT%20AIV%20iTPP%20v1%2013July2016/b-0010"),
    { kind: "block", blockId: "DRAFT AIV iTPP v1 13July2016/b-0010" },
  );
});

test("an unencoded id is unchanged", () => {
  assert.deepEqual(parseCitation("block:document/b-0010"), {
    kind: "block",
    blockId: "document/b-0010",
  });
});

test("malformed encoding costs its own link, not the answer", () => {
  // A stray % is not valid encoding; keep the raw text rather than throwing.
  assert.equal(parseCitation("block:doc%ZZ/b-1").kind, "block");
});
