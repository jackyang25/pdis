import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { fileURLToPath } from "node:url";
import { loadComponent } from "../test-support/load-component.ts";
import { reviewFixture } from "../test-support/scout-review-fixture.ts";
import { useAssistantReviewContext } from "./assistant-review-context.ts";

test("review context retains the current draft reference and cleanup cannot remove a newer panel", () => {
  const draft = reviewFixture("target_review");
  const before = JSON.stringify(draft);
  const store = useAssistantReviewContext.getState();
  store.publish({ owner: "old", draft, selection: null });
  assert.equal(useAssistantReviewContext.getState().active?.draft, draft);
  store.publish({ owner: "new", draft, selection: { kind: "target", target_id: "target" } });
  store.clear("old");
  assert.equal(useAssistantReviewContext.getState().active?.owner, "new");
  store.clear("new");
  assert.equal(useAssistantReviewContext.getState().active, null);
  assert.equal(JSON.stringify(draft), before, "publishing chat context does not mutate the result/export data");
  store.publish({ owner: "final", draft: { ...draft, phase: "final" }, selection: null });
  assert.equal(useAssistantReviewContext.getState().active, null);
});

test("workspace submits the active review separately, with source blocks, without counting it as a final result", () => {
  let active: unknown = { owner: "panel", draft: reviewFixture("target_review"), selection: { kind: "target", target_id: "target" } };
  let props: any;
  const emptySession = (selector: any) => selector({ results: [] });
  const { WorkspaceAsk } = loadComponent(fileURLToPath(new URL("../components/assistant/workspace-ask.tsx", import.meta.url)), {
    "next/navigation": { usePathname: () => "/scout" },
    "./ask": { Ask: (value: unknown) => { props = value; return null; } },
    "@/lib/session": Object.fromEntries(["Chunker", "Inspector", "Aligner", "Screener", "Scout", "Searcher"].map(name => [`use${name}Session`, emptySession])),
    "@/lib/priority-digest": { usePriorityDigestStore: (selector: any) => selector({ entries: {}, selected: {} }) },
    "@/lib/assistant-review-context": {
      ...loadComponent(fileURLToPath(new URL("./assistant-review-context.ts", import.meta.url))),
      useAssistantReviewContext: (selector: any) => selector({ active }),
    },
  });
  renderToStaticMarkup(React.createElement(WorkspaceAsk));
  assert.equal(props.result.active_review?.phase, "target_review");
  assert.equal(props.result.active_review.selected_item.target_id, "target");
  assert.equal(props.availableResultCount, 0);
  assert.deepEqual(props.result.results, []);
  assert.equal(props.result.blocks[0].id, "review:panel/seed-document/target");
  assert.equal(props.result.active_review.analysis.quantitative_ledger.targets[0].doc_block_ids[0], "review:panel/seed-document/target");
  assert.equal(props.result.active_review.analysis.blocks, undefined, "source bytes belong in the shared block collection once");
  active = null;
  renderToStaticMarkup(React.createElement(WorkspaceAsk));
  assert.equal(props.result.active_review, undefined);
  assert.deepEqual(props.result.blocks, []);
});

test("a draft of a revised same-name document cannot replace a final result's source", () => {
  const draft = reviewFixture("target_review");
  const final = { ...reviewFixture(), phase: "final" };
  final.conformity = [];
  final.blocks = final.blocks.map(block => ({ ...block, content: "Older original source text." }));
  const before = JSON.stringify(draft);
  let props: any;
  const emptySession = (selector: any) => selector({ results: [] });
  const sessions = Object.fromEntries(["Chunker", "Inspector", "Aligner", "Screener", "Scout", "Searcher"].map(name => [`use${name}Session`, emptySession]));
  // Use the parser's direct output to exercise retained final source collection,
  // independent of Scout final-contract eligibility in this focused test.
  sessions.useChunkerSession = (selector: any) => selector({ results: [{ id: "old", created_at: "2026-09-16", result: { doc_id: "seed-document", blocks: final.blocks } }] });
  const { WorkspaceAsk } = loadComponent(fileURLToPath(new URL("../components/assistant/workspace-ask.tsx", import.meta.url)), {
    "next/navigation": { usePathname: () => "/scout" },
    "./ask": { Ask: (value: unknown) => { props = value; return null; } },
    "@/lib/session": sessions,
    "@/lib/priority-digest": { usePriorityDigestStore: (selector: any) => selector({ entries: {}, selected: {} }) },
    "@/lib/assistant-review-context": {
      ...loadComponent(fileURLToPath(new URL("./assistant-review-context.ts", import.meta.url))),
      useAssistantReviewContext: (selector: any) => selector({ active: { owner: "panel", draft, selection: null } }),
    },
  });
  renderToStaticMarkup(React.createElement(WorkspaceAsk));
  assert.equal(props.result.blocks.length, 2);
  assert.equal(props.result.blocks.find((block: any) => block.id === "seed-document/target").content, "Older original source text.");
  const reviewBlock = props.result.blocks.find((block: any) => block.id === "review:panel/seed-document/target");
  assert.equal(reviewBlock.content, "Target protective efficacy is at least 80%.");
  assert.notEqual(reviewBlock.doc_id, "seed-document");
  assert.equal(reviewBlock.structural_meta.source_block_id, "seed-document/target");
  assert.equal(JSON.stringify(draft), before);
});
