/**
 * Marking a quote inside its passage, without losing the passage or the quote.
 *
 * The invariant every test here checks from a different angle: joining the segments returns
 * the original passage, character for character. A highlight that silently rewrites the text
 * it highlights would be worse than no highlight, because the passage is the evidence.
 *
 * The whitespace tests are the load-bearing ones. On a real run 15 of 36 quotes matched their
 * block only after runs of spaces were collapsed, so an implementation that matched literally
 * would have dropped the highlight on nearly half of them.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";

import { markCitedText } from "./cited-text.ts";

const joined = (content: string, quotes: string[]) =>
  markCitedText(content, quotes)
    .segments.map((segment) => segment.text)
    .join("");

const cited = (content: string, quotes: string[]) =>
  markCitedText(content, quotes)
    .segments.filter((segment) => segment.cited)
    .map((segment) => segment.text);

test("the passage is returned unchanged, character for character", () => {
  const content = "The oral run-in could be short (e.g., 1 week) but no longer than 2 months.";
  assert.equal(joined(content, ["could be short"]), content);
});

test("the quote is the marked run, and nothing else is", () => {
  const content = "Shelf life: minimum 24 months at 2-8C; optimal 36 months.";
  assert.deepEqual(cited(content, ["minimum 24 months"]), ["minimum 24 months"]);
});

test("a quote whose spacing differs from the passage still lands", () => {
  // The real case: the quote was captured from a table row and the parse renders it with
  // different spacing. A literal `includes` fails here, and 15 of 36 real quotes are like it.
  const content = "NOTE:  Drugs in LAIs same as drugs\nin oral run-in (or subset)";
  const result = markCitedText(content, ["Drugs in LAIs same as drugs in oral run-in"]);
  assert.deepEqual(result.unplaced, []);
  assert.equal(joined(content, ["Drugs in LAIs same as drugs in oral run-in"]), content);
  // The marked run keeps the passage's own spacing, not the quote's.
  assert.match(cited(content, ["Drugs in LAIs same as drugs in oral run-in"])[0], /\n/);
});

test("two quotes in one passage are both marked", () => {
  const content = "Shelf life: minimum 24 months at 2-8C; optimal 36 months.";
  assert.deepEqual(cited(content, ["minimum 24 months", "optimal 36 months"]), [
    "minimum 24 months",
    "optimal 36 months",
  ]);
});

test("marked runs come out in passage order, not the order they were given", () => {
  const content = "first part then second part";
  assert.deepEqual(cited(content, ["second part", "first part"]), [
    "first part",
    "second part",
  ]);
});

test("a repeated quote claims one occurrence per quote, not the same one twice", () => {
  const content = "24 months, then 24 months again";
  const result = markCitedText(content, ["24 months"]);
  assert.deepEqual(
    result.segments.filter((segment) => segment.cited).length,
    1,
    "one quote marks one run",
  );
});

test("a quote that is not in the passage is reported, never dropped", () => {
  // The safety net. Removing the separate quote box is only safe because of this: a quote
  // that cannot be placed is handed back so the caller can still show it.
  const content = "Shelf life: minimum 24 months.";
  const result = markCitedText(content, ["a sentence from somewhere else"]);
  assert.deepEqual(result.unplaced, ["a sentence from somewhere else"]);
  assert.equal(joined(content, ["a sentence from somewhere else"]), content);
});

test("some quotes placed and some not is reported precisely", () => {
  const content = "Shelf life: minimum 24 months.";
  const result = markCitedText(content, ["minimum 24 months", "not present here"]);
  assert.deepEqual(result.unplaced, ["not present here"]);
  assert.deepEqual(
    result.segments.filter((segment) => segment.cited).map((segment) => segment.text),
    ["minimum 24 months"],
  );
});

test("no quotes leaves the passage whole and unmarked", () => {
  const content = "Just the passage.";
  const result = markCitedText(content, []);
  assert.deepEqual(result.segments, [{ text: content, cited: false }]);
  assert.deepEqual(result.unplaced, []);
});

test("a blank quote is ignored rather than matching everywhere", () => {
  const content = "Just the passage.";
  const result = markCitedText(content, ["", "   "]);
  assert.deepEqual(result.segments, [{ text: content, cited: false }]);
  assert.deepEqual(result.unplaced, []);
});

test("an empty passage reports its quotes as unplaced", () => {
  assert.deepEqual(markCitedText("", ["something"]), {
    segments: [],
    unplaced: ["something"],
  });
});

test("a quote covering the whole passage marks all of it and adds nothing", () => {
  const content = "Exactly the whole thing.";
  const result = markCitedText(content, [content]);
  assert.deepEqual(result.segments, [{ text: content, cited: true }]);
});

test("leading and trailing whitespace in the passage is preserved", () => {
  // The segments are sliced from the original, so indentation a table row carries survives.
  const content = "  indented line with a quote inside  ";
  assert.equal(joined(content, ["a quote inside"]), content);
});

test("the same quote given twice is treated as one", () => {
  const content = "minimum 24 months at 2-8C";
  const result = markCitedText(content, ["minimum 24 months", "minimum 24 months"]);
  assert.equal(result.segments.filter((segment) => segment.cited).length, 1);
  assert.deepEqual(result.unplaced, []);
});

test("both tools locate a cited quote the same way", () => {
  // Scout's document trace and Archivist's provenance both mark a quote inside its block.
  // Archivist had its own `indexOf` version, which worked only because its own invariant
  // guarantees an exact match; Scout's real data showed that 15 of 36 quotes differ from
  // their block by whitespace alone. One locator, so the two cannot answer differently.
  const files = ["components/document-source-trace.tsx", "app/archivist/page.tsx"];
  for (const file of files) {
    const text = readFileSync(path.resolve(import.meta.dirname, "..", file), "utf8");
    assert.ok(
      text.includes("markCitedText"),
      `${file} no longer uses the shared locator`,
    );
    assert.ok(
      !/\.indexOf\((?:record|selectedBlock)?\.?quote\)/.test(text),
      `${file} has gone back to locating a quote by hand`,
    );
  }
});
