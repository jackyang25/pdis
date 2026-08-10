/**
 * The wire format the API frames and this transport reads.
 *
 * Streaming worked locally and not in production because Cloudflare buffers
 * `text/plain` to completion. The fix is the media type, which means the body is
 * now events rather than raw text — so the two halves have to agree, and a
 * chunk boundary landing mid-event must not truncate an answer.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";

import { readEvent } from "./assistant-transport.ts";

const REPO = path.resolve(import.meta.dirname, "..", "..");
const ROUTE = path.join(REPO, "api", "routes", "assistant.py");

test("the API frames what this file parses", () => {
  const source = readFileSync(ROUTE, "utf8");
  assert.match(source, /media_type="text\/event-stream"/,
    "the route no longer sends events, so this transport cannot read it");
  assert.match(source, /json\.dumps\(chunk\.text\)/,
    "the route no longer JSON-encodes each payload");
  assert.match(source, /event: \{chunk\.kind\}/,
    "the route no longer marks activity as its own event kind");
});

test("an unmarked event is the answer", () => {
  // Text is the SSE default, so the common case carries no marker at all.
  assert.deepEqual(readEvent('data: "The target is 80%."'), {
    kind: "text",
    text: "The target is 80%.",
  });
});

test("a marked event is activity, on its own channel", () => {
  // What replaced a control character inside the text: the format already
  // distinguishes kinds, so nothing has to be parsed back out of the answer.
  assert.deepEqual(readEvent('event: activity\ndata: "Reading the analysis"'), {
    kind: "activity",
    text: "Reading the analysis",
  });
});

test("an unknown event kind is treated as answer text, not dropped", () => {
  assert.deepEqual(readEvent('event: something-new\ndata: "words"'), {
    kind: "text",
    text: "words",
  });
});

test("a newline inside prose does not end the event", () => {
  // Why each chunk is JSON on the wire: SSE is line-delimited and model prose
  // contains newlines constantly.
  assert.equal(readEvent('data: "one\\ntwo"')?.text, "one\ntwo");
});

test("several data lines in one event are joined", () => {
  assert.equal(readEvent('data: "a"\ndata: "b"')?.text, "ab");
});

test("an event carrying no data yields nothing", () => {
  assert.equal(readEvent(": keepalive"), null);
  assert.equal(readEvent(""), null);
});

test("a malformed line costs its own text, not the answer", () => {
  // One bad event should not abort a stream that is otherwise fine.
  assert.equal(readEvent('data: not-json\ndata: "kept"')?.text, "kept");
  assert.equal(readEvent("data: not-json"), null);
});

test("a non-string payload is ignored rather than rendered", () => {
  assert.equal(readEvent("data: 42"), null);
  assert.equal(readEvent('data: {"a":1}'), null);
});
