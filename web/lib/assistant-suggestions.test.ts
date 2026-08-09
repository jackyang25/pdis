/**
 * Every tool that produces a result offers openers, and none of them promises
 * something its tool does not do.
 *
 * Three tools had no entry and fell through to a single generic line, so Expert,
 * Chunker, and Searcher each opened with one chip while the others opened with
 * two. The gap was invisible because the fallback was valid text.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";

import { WORKSPACE_TOOLS } from "./tools.ts";

const ASK = path.resolve(import.meta.dirname, "..", "components", "assistant", "ask.tsx");

/** The declared openers, read from source so the test needs no client render. */
function suggestions(): Record<string, string[]> {
  const source = readFileSync(ASK, "utf8");
  const block = /const SUGGESTIONS: Record<string, string\[\]> = \{(.*?)\n\};/s.exec(source);
  assert.ok(block, "ask.tsx no longer declares SUGGESTIONS");
  const entries: Record<string, string[]> = {};
  for (const line of block[1].split("\n")) {
    const match = /^\s{2}(\w+): \[(.+)\],$/.exec(line);
    if (!match) continue;
    entries[match[1]] = [...match[2].matchAll(/"([^"]+)"/g)].map((m) => m[1]);
  }
  return entries;
}

test("every available workspace tool offers its own openers", () => {
  const declared = suggestions();
  for (const tool of WORKSPACE_TOOLS) {
    if (tool.availability !== "available") continue;
    with_(tool.id, () => {
      assert.ok(declared[tool.id], `${tool.id} falls through to the generic openers`);
    });
  }
});

test("each tool offers exactly two, so no tool opens narrower than another", () => {
  for (const [tool, openers] of Object.entries(suggestions())) {
    assert.equal(openers.length, 2, `${tool} offers ${openers.length}`);
  }
});

test("a tool that renders no verdict is not asked for one", () => {
  // Chunker parses and Searcher retrieves; neither judges. An opener implying
  // otherwise would invite an assessment the result does not contain.
  const declared = suggestions();
  for (const tool of ["chunker", "searcher"]) {
    const text = declared[tool].join(" ").toLowerCase();
    for (const verdict of ["attention", "weakest", "fall short", "conflict"]) {
      assert.ok(
        !text.includes(verdict),
        `${tool} opener implies a judgment it does not make: "${text}"`,
      );
    }
  }
});

test("openers are questions a reader can act on, not commands", () => {
  for (const [tool, openers] of Object.entries(suggestions())) {
    for (const opener of openers) {
      assert.ok(opener.trim().length > 10, `${tool}: "${opener}" is too terse`);
    }
  }
});

function with_(name: string, body: () => void) {
  try {
    body();
  } catch (error) {
    (error as Error).message = `${name}: ${(error as Error).message}`;
    throw error;
  }
}
