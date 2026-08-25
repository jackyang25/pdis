/**
 * Deep links from a signal tooltip to the prompt behind it.
 *
 * Written because this was broken in a way nothing could notice. Every "Read the
 * instructions behind this" link landed at the same place on the docs page, whichever
 * prompt it named: the handler looked the anchor up before loading the file that renders
 * it, found nothing, and returned early — so the load it would have triggered never ran.
 * A link that scrolls to the wrong place looks like a page that simply did not scroll.
 *
 * The scroll itself needs a browser. What is checkable here is that each link names a
 * prompt that exists, and that an anchor is matched to the right tool.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";

import {
  isPromptAnchorFor,
  promptAnchor,
  promptHref,
  type ToolKey,
} from "./prompt-reference.ts";

const REPO = path.resolve(import.meta.dirname, "..", "..");

/** The published artifact the docs page fetches, read as it ships. */
function publishedPrompts(): { tool: string; stage: string }[] {
  const raw = readFileSync(path.join(REPO, "shared", "prompt_reference.json"), "utf8");
  return (JSON.parse(raw) as { prompts: { tool: string; stage: string }[] }).prompts;
}

/** Every `promptRef` a Scout signal tooltip offers. */
function signalPromptRefs(): { tool: string; stage: string }[] {
  const help = readFileSync(
    path.join(REPO, "web", "components", "scout-signal-help.tsx"),
    "utf8",
  );
  return [...help.matchAll(/promptRef:\s*\{\s*tool:\s*"([^"]+)",\s*stage:\s*"([^"]+)"\s*\}/g)]
    .map((match) => ({ tool: match[1], stage: match[2] }));
}

test("every signal links to a prompt that is actually published", () => {
  // A stage renamed in the catalog leaves the tooltip pointing at an anchor no page
  // renders, which fails silently: the link opens the docs and stops.
  const published = publishedPrompts();
  const refs = signalPromptRefs();
  assert.equal(refs.length, 4, "expected one prompt link per Scout result axis");
  for (const ref of refs) {
    assert.ok(
      published.some((prompt) => prompt.tool === ref.tool && prompt.stage === ref.stage),
      `no published prompt for ${ref.tool}/${ref.stage}`,
    );
  }
});

test("the four signals point at four different prompts", () => {
  // The symptom that started this: four links, one destination. They were distinct in the
  // data even then, so distinctness alone did not prove the links worked — but a
  // duplicate here would be a second, simpler way to arrive at the same failure.
  const anchors = signalPromptRefs().map((ref) => promptAnchor(ref.tool as ToolKey, ref.stage));
  assert.equal(new Set(anchors).size, anchors.length, `two signals share an anchor: ${anchors}`);
});

test("a prompt link carries a fragment, not just the docs page", () => {
  assert.equal(
    promptHref("scout", "evidence_assessor"),
    "/docs#prompt-scout-evidence_assessor",
  );
});

test("an anchor is matched to the tool that owns it", () => {
  // The docs page renders one section per tool, each holding its own copy of the
  // reference. Matching loosely would make all five fetch 100 KB to serve a link naming
  // one of them.
  assert.equal(isPromptAnchorFor("prompt-scout-evidence_assessor", "scout"), true);
  assert.equal(isPromptAnchorFor("prompt-scout-evidence_assessor", "inspector"), false);
});

test("a fragment that is not a prompt anchor matches no tool", () => {
  // The docs page uses ordinary section anchors too; the handler must ignore them rather
  // than treat every hash change as a prompt link.
  for (const tool of ["chunker", "inspector", "aligner", "expert", "scout"] as ToolKey[]) {
    assert.equal(isPromptAnchorFor("architecture", tool), false);
    assert.equal(isPromptAnchorFor("", tool), false);
  }
});

test("no tool's anchors are a prefix of another's", () => {
  // What `isPromptAnchorFor` rests on. A tool named `scout2` would make every
  // `prompt-scout-…` link load that section too.
  const tools: ToolKey[] = ["chunker", "inspector", "aligner", "expert", "scout"];
  for (const tool of tools) {
    for (const other of tools) {
      if (tool === other) continue;
      assert.equal(
        isPromptAnchorFor(promptAnchor(other, "any_stage"), tool),
        false,
        `${other}'s anchors match ${tool}`,
      );
    }
  }
});
