import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { fileURLToPath } from "node:url";
import { loadComponent } from "../test-support/load-component.ts";
import { citationSources } from "./citation.ts";

// Exercise event handlers across renders without a DOM. Network and SDK state
// are boundaries; the real Ask handlers own every state transition asserted here.
function chatHarness(upload: () => Promise<unknown>) {
  const slots: any[] = [];
  let cursor = 0;
  let messages: any[] = [{ id: "existing", role: "user", parts: [{ type: "text", text: "Earlier question" }] }];
  const { Ask } = loadComponent(fileURLToPath(new URL("../components/assistant/ask.tsx", import.meta.url)), {
    react: { ...React,
      useState: (initial: unknown) => {
        const index = cursor++;
        if (!(index in slots)) slots[index] = initial;
        return [slots[index], (next: any) => { slots[index] = typeof next === "function" ? next(slots[index]) : next; }];
      },
      useRef: (initial: unknown) => {
        const index = cursor++;
        return slots[index] ??= { current: initial };
      },
      useMemo: (factory: () => unknown) => factory(), useEffect: () => {},
    },
    "@/lib/api": { API_BASE: "", uploadAssistantContext: upload },
    "@ai-sdk/react": { useChat: () => ({ messages, status: "ready", stop: () => {},
      setMessages: (next: any[]) => { messages = next; }, clearError: () => {}, sendMessage: async () => {},
    }) },
  });
  return (result: unknown) => { cursor = 0; return Ask({ resultType: "workspace", result, display: "page" }); };
}

function findElement(node: any, predicate: (props: any) => boolean): any {
  if (!node || typeof node !== "object") return;
  if (node.props && predicate(node.props)) return node;
  for (const child of React.Children.toArray(node.props?.children)) {
    const found = findElement(child, predicate);
    if (found) return found;
  }
}

test("receiving a result never aborts a reply or clears the conversation", () => {
  const effects: (() => unknown)[] = [];
  let stops = 0;
  let clears = 0;
  const { Ask } = loadComponent(fileURLToPath(new URL("../components/assistant/ask.tsx", import.meta.url)), {
    react: { ...React, useEffect: (effect: () => unknown) => effects.push(effect) },
    "@ai-sdk/react": { useChat: () => ({
      messages: [], status: "streaming", error: undefined,
      stop: () => { stops++; }, setMessages: () => { clears++; },
      clearError: () => {}, sendMessage: async () => {},
    }) },
  });
  renderToStaticMarkup(React.createElement(Ask, {
    resultType: "workspace", result: { results: [{ id: "new-result" }], blocks: [] }, display: "page",
  }));
  effects.forEach(effect => effect());
  assert.equal(stops, 0, "context updates must not stop the active response");
  assert.equal(clears, 0, "context updates must not clear messages");
});

test("rendered old citations use their original block and URL after a same-name document is replaced", () => {
  const sources = loadComponent(fileURLToPath(new URL("../components/document-source-trace.tsx", import.meta.url)));
  const old = {
    resultType: "workspace", result: {},
    document: [{ id: "doc/block", content: "Original passage" }],
    sources: citationSources({ url: "https://example.org/original" }),
  };
  const { Ask } = loadComponent(fileURLToPath(new URL("../components/assistant/ask.tsx", import.meta.url)), {
    react: { ...React, useRef: (value: unknown) => React.useRef(value instanceof Map ? new Map([["old", old]]) : value) },
    "@ai-sdk/react": { useChat: () => ({
      messages: [
        { id: "q", role: "user", parts: [{ type: "text", text: "Explain" }], metadata: { contextId: "old" } },
        { id: "a", role: "assistant", parts: [{ type: "text", text: "[Passage](block:doc/block) [Paper](https://example.org/original)" }] },
      ], status: "ready", stop: () => {}, setMessages: () => {}, clearError: () => {}, sendMessage: async () => {},
    }) },
    "@/components/document-source-trace": sources,
    "./block-citation": { BlockCitation: () => {
      const { blocks } = React.useContext(sources.DocumentSourceContext) as { blocks: { content: string }[] };
      return React.createElement("span", null, blocks[0]?.content);
    } },
  });
  const html = renderToStaticMarkup(React.createElement(Ask, {
    resultType: "workspace", display: "page",
    result: { blocks: [{ id: "doc/block", content: "Replacement passage" }] },
  }));
  assert.match(html, /Original passage/);
  assert.doesNotMatch(html, /Replacement passage/);
  assert.match(html, /href="https:\/\/example.org\/original"/);
  assert.match(html, /earlier workspace context/);
});

test("a result update preserves unsent text, while New chat rejects an upload finishing from the old conversation", async () => {
  let finishUpload!: (value: unknown) => void;
  const render = chatHarness(() => new Promise(resolve => { finishUpload = resolve; }));
  let tree = render({ results: [], blocks: [] });
  findElement(tree, props => props.placeholder === "Ask about tools or results…").props.onChange({ target: { value: "Unsent question" } });
  const input = findElement(tree, props => props.type === "file");
  input.props.onChange({ target: { files: [{ name: "old.docx" }] } });
  tree = render({ results: [{ id: "finished" }], blocks: [] });
  assert.equal(findElement(tree, props => props.placeholder === "Ask about tools or results…").props.value, "Unsent question");
  findElement(tree, props => props["aria-label"] === "New chat").props.onClick();
  finishUpload({ filename: "old.docx", doc_id: "old", blocks: [] });
  await new Promise(resolve => setImmediate(resolve));
  tree = render({ results: [{ id: "finished" }], blocks: [] });
  assert.equal(findElement(tree, props => props.placeholder === "Ask about tools or results…").props.value, "");
  assert.equal(findElement(tree, props => props["aria-label"] === "Remove old.docx"), undefined);
});
