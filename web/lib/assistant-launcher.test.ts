/**
 * The assistant costs nothing until it is opened.
 *
 * Every page mounts the shell's assistant, so it used to ship the chat - a Markdown parser,
 * the AI SDK and its transport - to every reader and rebuild the workspace bundle, hashing
 * every held document, on every change to any tool's history, with the panel closed.
 */

import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { fileURLToPath } from "node:url";
import { loadComponent } from "../test-support/load-component.ts";

function workspace(pathname: string) {
  const calls = { resolved: 0, mounted: 0, loaded: 0 };
  const draft = { id: "draft-1", created_at: "2026-10-21", result: { indication: "malaria", variables: [] } };
  const sessions = Object.fromEntries(
    ["Chunker", "Inspector", "Aligner", "Screener", "Drafter", "Scout", "Searcher"].map((name) => [
      `use${name}Session`,
      (selector: any) => selector({ results: name === "Drafter" ? [draft] : [] }),
    ]),
  );
  const { WorkspaceAsk } = loadComponent(fileURLToPath(new URL("../components/assistant/workspace-ask.tsx", import.meta.url)), {
    "next/navigation": { usePathname: () => pathname },
    "next/dynamic": (load: () => Promise<unknown>) => {
      calls.loaded += 1;
      void load;
      return () => { calls.mounted += 1; return null; };
    },
    "@/lib/session": sessions,
    "@/lib/priority-reading": { usePriorityReadingStore: (selector: any) => selector({ entries: {} }) },
    "@/lib/assistant-review-context": {
      reviewContextForAssistant: () => null,
      useAssistantReviewContext: (selector: any) => selector({ active: null }),
    },
    "@/lib/workspace-documents": {
      resolveDocumentVersions: (runs: unknown[]) => { calls.resolved += 1; return runs; },
    },
  });
  return { html: renderToStaticMarkup(React.createElement(WorkspaceAsk)), calls };
}

test("a closed assistant shows its launcher and count without loading the chat or building the bundle", () => {
  const { html, calls } = workspace("/drafter");
  assert.match(html, /PDIS Assistant/);
  assert.match(html, />1<\/span>/, "the launcher lost the count of results it can read");
  assert.equal(calls.mounted, 0, "the chat was mounted before anyone opened it");
  assert.equal(calls.resolved, 0, "the workspace bundle was built for a closed panel");
});

test("the full-page assistant mounts the chat and builds the bundle at once", () => {
  const { calls } = workspace("/ask");
  assert.equal(calls.mounted, 1);
  assert.equal(calls.resolved, 1);
});
