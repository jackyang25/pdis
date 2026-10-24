/**
 * How a tool route's NDJSON stream is read: every event, however the bytes arrive.
 */

import assert from "node:assert/strict";
import test from "node:test";

import { runChunker } from "./api.ts";

function streamOf(chunks: Uint8Array[]): Response {
  return new Response(new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(chunk);
      controller.close();
    },
  }));
}

const header = { org: "bmgf", source_type: "itpp", intervention_class: "vaccine", indication: "malaria" };

test("events split across chunks, mid-character, still arrive whole", async (t) => {
  const result = { doc_id: "Plan", blocks: [{ id: "Plan/b-1", content: "Dosis – año" }] };
  const bytes = new TextEncoder().encode(
    `${JSON.stringify({ event: "stage", name: "parse" })}\n${JSON.stringify({ event: "complete", result })}\n`,
  );
  // Cut inside the en dash, whose UTF-8 form is three bytes.
  const cut = bytes.indexOf(0xe2) + 1;
  t.mock.method(globalThis, "fetch", async () => streamOf([bytes.slice(0, 7), bytes.slice(7, cut), bytes.slice(cut)]));
  const stages: string[] = [];
  assert.deepEqual(await runChunker(new File(["x"], "Plan.docx"), header as never, (stage) => stages.push(stage)), result);
  assert.deepEqual(stages, ["parse"]);
});

test("a final event without a trailing newline is not lost", async (t) => {
  const result = { doc_id: "Plan", blocks: [] };
  t.mock.method(globalThis, "fetch", async () => streamOf([
    new TextEncoder().encode(JSON.stringify({ event: "complete", result })),
  ]));
  assert.deepEqual(await runChunker(new File(["x"], "Plan.docx"), header as never), result);
});

test("a refused request says the server's sentence, not its JSON", async (t) => {
  t.mock.method(globalThis, "fetch", async () =>
    new Response(JSON.stringify({ detail: "Unsupported file type." }), { status: 400 }));
  await assert.rejects(runChunker(new File(["x"], "Plan.docx"), header as never, () => {}), { message: "Unsupported file type." });
});

test("a malformed request lists what was wrong, and a bare status still says something", async () => {
  const { responseError } = await import("./api.ts");
  const listed = await responseError(new Response(JSON.stringify({ detail: [{ msg: "field required" }, { msg: "too long" }] }), { status: 422 }));
  assert.equal(listed.message, "field required; too long");
  assert.equal((await responseError(new Response("", { status: 503 }))).message, "Request failed (503)");
});

test("a server that cannot be reached is said in words", async (t) => {
  t.mock.method(globalThis, "fetch", async () => { throw new TypeError("Failed to fetch"); });
  await assert.rejects(runChunker(new File(["x"], "Plan.docx"), header as never, () => {}), /Could not reach the PDIS server/);
});

test("a connection that breaks mid-run says the run stopped, not the browser's 'network error'", async (t) => {
  const stage = new TextEncoder().encode(`${JSON.stringify({ event: "stage", name: "parse" })}\n`);
  t.mock.method(globalThis, "fetch", async () => new Response(new ReadableStream({
    start(controller) {
      controller.enqueue(stage);
      controller.error(new TypeError("network error"));
    },
  })));
  await assert.rejects(runChunker(new File(["x"], "Plan.docx"), header as never, () => {}), /The run stopped before it finished/);
});
