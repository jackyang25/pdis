/**
 * The activity line is a protocol shared with `services/assistant/agent.py`.
 *
 * It travels in the same stream as the answer, so the two failures that matter
 * are opposite: a delimiter reaching the reader as prose, and an announcement
 * being read as part of the answer. Both are pinned here, along with the
 * partial-stream case, since this runs on every token.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";

import { ACTIVITY_DELIMITER, readAssistantStream } from "./assistant-stream.ts";

const REPO = path.resolve(import.meta.dirname, "..", "..");
const AGENT = path.join(REPO, "services", "assistant", "agent.py");
const D = ACTIVITY_DELIMITER;

test("the delimiter matches the agent that writes it", () => {
  const source = readFileSync(AGENT, "utf8");
  const declared = /ACTIVITY_DELIMITER\s*=\s*"\\x([0-9a-fA-F]{2})"/.exec(source);
  assert.ok(declared, "agent.py no longer declares ACTIVITY_DELIMITER");
  assert.equal(
    D,
    String.fromCharCode(parseInt(declared[1], 16)),
    "web/lib/assistant-stream.ts drifted from services/assistant/agent.py",
  );
});

test("plain prose passes through untouched", () => {
  assert.deepEqual(readAssistantStream("The target is 80%."), {
    text: "The target is 80%.",
    activity: null,
  });
});

test("an announcement is shown as activity and never as prose", () => {
  const { text, activity } = readAssistantStream(`${D}Reading the analysis${D}`);
  assert.equal(text, "");
  assert.equal(activity, "Reading the analysis");
});

test("a half-arrived announcement is withheld rather than shown raw", () => {
  // Tokens arrive one at a time; the delimiter must never reach the reader.
  const { text, activity } = readAssistantStream(`${D}Reading the ana`);
  assert.equal(text, "", "an unterminated label must not render as the answer");
  assert.equal(activity, null, "a partial label must not be shown either");
});

test("the answer replaces the activity once it starts", () => {
  const { text, activity } = readAssistantStream(
    `${D}Reading the analysis${D}The target is 80%.`,
  );
  assert.equal(text, "The target is 80%.");
  assert.equal(activity, null, "work has finished once prose arrives");
});

test("the latest of several announcements is the current one", () => {
  const { text, activity } = readAssistantStream(
    `${D}Searching the analysis${D}${D}Opening a cited source${D}`,
  );
  assert.equal(text, "");
  assert.equal(activity, "Opening a cited source");
});

test("prose either side of an announcement is joined, not split", () => {
  const { text } = readAssistantStream(`Before ${D}Reading the analysis${D}after.`);
  assert.equal(text, "Before after.");
});
