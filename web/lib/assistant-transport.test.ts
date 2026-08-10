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

import { AssistantSseTransport, readEvent } from "./assistant-transport.ts";

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

test("the chunk sequence is one the SDK can build a message from", async () => {
  // The failure this exists for: deltas alone render blank. The SDK assembles a
  // message from an envelope, and omitting it produced an empty answer that
  // every parser test still passed.
  const body = [
    'event: activity\ndata: "Reading the analysis"\n\n',
    'data: "The target "\n\n',
    'data: "is 80%."\n\n',
  ].join("");

  const chunks = await collect(body);
  const kinds = chunks.map((chunk) => chunk.type);

  assert.deepEqual(kinds, [
    "start",
    "start-step",
    "data-activity",
    "text-start",
    "text-delta",
    "text-delta",
    "text-end",
    "finish-step",
    "finish",
  ]);
});

test("an answer arrives in the order it was streamed", async () => {
  const chunks = await collect('data: "one "\n\ndata: "two"\n\n');
  const text = chunks
    .filter((chunk) => chunk.type === "text-delta")
    .map((chunk) => (chunk as unknown as { delta: string }).delta)
    .join("");
  assert.equal(text, "one two");
});

test("an event split across network chunks is not truncated", async () => {
  // A read boundary can land anywhere; a partial event waits for its terminator.
  const chunks = await collect(['data: "half', ' and half"\n\n'], true);
  const text = chunks
    .filter((chunk) => chunk.type === "text-delta")
    .map((chunk) => (chunk as unknown as { delta: string }).delta)
    .join("");
  assert.equal(text, "half and half");
});

test("a turn with no answer still closes the message", async () => {
  const kinds = (await collect('event: activity\ndata: "Working"\n\n')).map((c) => c.type);
  assert.deepEqual(kinds, ["start", "start-step", "data-activity", "finish-step", "finish"]);
});

/** Drive the real transport over a body, optionally split into network chunks. */
async function collect(body: string | string[], preSplit = false) {
  const pieces = preSplit ? (body as string[]) : [body as string];
  const encoder = new TextEncoder();
  const source = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const piece of pieces) controller.enqueue(encoder.encode(piece));
      controller.close();
    },
  });
  const transport = new AssistantSseTransport({ api: "/unused" });
  // `processResponseStream` is the one method a transport implements; reading it
  // directly is what tests the contract rather than the SDK's plumbing.
  const stream = (
    transport as unknown as {
      processResponseStream(s: ReadableStream<Uint8Array>): ReadableStream<{ type: string }>;
    }
  ).processResponseStream(source);
  const out: { type: string }[] = [];
  const reader = stream.getReader();
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    out.push(value);
  }
  return out;
}
