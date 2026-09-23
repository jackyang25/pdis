import assert from "node:assert/strict";
import test from "node:test";
import { assistantRequest, conversationTurns, type AskContext, type AskMessage } from "./assistant-conversation.ts";
import { citationSources, parseCitation } from "./citation.ts";
import { Chat } from "@ai-sdk/react";
import { AssistantSseTransport } from "./assistant-transport.ts";

function context(text: string): AskContext {
  return {
    resultType: "workspace",
    result: { label: text, url: `https://example.org/${text}` },
    document: [{ id: "same-document/block", content: text }] as AskContext["document"],
    sources: citationSources({ url: `https://example.org/${text}` }),
  };
}
const contextId = (snapshot: AskContext) => (snapshot.result as { label: string }).label;
const contextsFor = (...snapshots: AskContext[]) => new Map(snapshots.map(snapshot => [contextId(snapshot), snapshot]));
const question = (id: string, snapshot: AskContext): AskMessage => ({
  id, role: "user", parts: [{ type: "text", text: "Explain this." }], metadata: { contextId: contextId(snapshot) },
});
const answer = (id: string): AskMessage => ({ id, role: "assistant", parts: [{ type: "text", text: "See [source](block:same-document/block)." }] });

test("a submitted turn stays pinned when a newer result arrives before request preparation", () => {
  const old = context("original");
  const current = context("replacement");
  const request = assistantRequest([question("q1", old)], current, contextsFor(old, current));
  assert.deepEqual(request.result, { label: "original", url: "https://example.org/original" });
  assert.equal(request.document[0].content, "original");
  assert.equal(JSON.stringify(request).includes('"metadata"'), false);
});

test("the next turn uses new evidence and marks older conversation as historical", () => {
  const old = context("original");
  const current = context("replacement");
  const messages = [question("q1", old), answer("a1"), question("q2", current)];
  const request = assistantRequest(messages, current, contextsFor(old, current));
  assert.equal(request.document[0].content, "replacement");
  assert.equal(request.messages.length, 3);
  assert.match(request.messages[0].content, /earlier workspace context/i);
  assert.match(request.messages[1].content, /earlier workspace context/i);
  assert.match(request.messages[2].content, /current workspace context/i);
  assert.equal(JSON.stringify(request).includes('"content":"original"'), false, "old source bytes are not resent");
});

test("old and streaming answers resolve same-name blocks and URLs against their own turn", () => {
  const old = context("original");
  const current = context("replacement");
  const turns = conversationTurns([question("q1", old), answer("a1"), question("q2", current), answer("streaming")], contextsFor(old, current));
  assert.equal(turns[1].context?.document[0].content, "original");
  assert.equal(turns[3].context?.document[0].content, "replacement");
  assert.equal(parseCitation("https://example.org/original", turns[1].context!.sources).kind, "external");
  assert.equal(parseCitation("https://example.org/replacement", turns[1].context!.sources).kind, "plain");
});

test("an empty new conversation retains no old source snapshot", () => {
  assert.deepEqual(conversationTurns([], new Map()), []);
  assert.deepEqual(assistantRequest([], context("current"), new Map()).messages, []);
});

test("real streaming chat keeps the first request frozen and sends updated context on the next question", async () => {
  let current = context("original");
  const contexts = contextsFor(current);
  const requests: ReturnType<typeof assistantRequest>[] = [];
  let finishFirst!: () => void;
  let firstStarted!: () => void;
  const started = new Promise<void>(resolve => { firstStarted = resolve; });
  const transport = new AssistantSseTransport<AskMessage>({
    api: "https://example.org/ask",
    prepareSendMessagesRequest: ({ messages }) => ({ body: assistantRequest(messages, current, contexts) }),
    fetch: async (_url, init) => {
      requests.push(JSON.parse(String(init?.body)));
      const encoder = new TextEncoder();
      return new Response(new ReadableStream({ start(controller) {
        controller.enqueue(encoder.encode('data: "Answer"\n\n'));
        const finish = () => {
          controller.enqueue(encoder.encode('event: done\ndata: {}\n\n'));
          controller.close();
        };
        if (requests.length === 1) { finishFirst = finish; firstStarted(); }
        else finish();
      } }), { headers: { "Content-Type": "text/event-stream" } });
    },
  });
  const chat = new Chat<AskMessage>({ transport });
  const first = chat.sendMessage({ text: "First question", metadata: { contextId: contextId(current) } });
  await started;
  current = context("replacement");
  contexts.set(contextId(current), current);
  finishFirst();
  await first;
  assert.equal(chat.status, "ready");
  assert.equal(requests[0].document[0].content, "original");
  assert.equal(conversationTurns(chat.messages, contexts)[1].context?.document[0].content, "original");
  await chat.sendMessage({ text: "Next question", metadata: { contextId: contextId(current) } });
  assert.equal(chat.messages.length, 4);
  assert.equal(requests[1].document[0].content, "replacement");
  assert.match(requests[1].messages[0].content, /earlier workspace context/i);
  assert.match(requests[1].messages[2].content, /current workspace context/i);
  chat.messages = [];
  assert.deepEqual(conversationTurns(chat.messages, contexts), []);
});
