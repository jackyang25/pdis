import assert from "node:assert/strict";
import test from "node:test";

import { EXTERNAL_TOOLS, WORKSPACE_TOOLS } from "./tools.ts";
import { ALL_TOOLS, TOOL_SECTIONS, sectionTools } from "./tool-sections.ts";

test("every id a section lists resolves to a defined tool", () => {
  const known = new Set(ALL_TOOLS.map((tool) => tool.id));
  for (const section of TOOL_SECTIONS) {
    for (const id of section.toolIds) {
      assert.ok(known.has(id), `${section.id} lists unknown tool "${id}"`);
    }
  }
});

test("every tool appears in exactly one section", () => {
  const placed = TOOL_SECTIONS.flatMap((section) => [...section.toolIds]);
  assert.deepEqual(
    [...placed].sort(),
    [...ALL_TOOLS.map((tool) => tool.id)].sort(),
    "a tool is missing from the landing page or placed in two sections",
  );
  assert.equal(new Set(placed).size, placed.length);
});

// The anti-drift assertion. The docs tool list and the Ask catalog both walk
// WORKSPACE_TOOLS then EXTERNAL_TOOLS with no sorting, so a section that ordered
// its ids differently would make one surface list the tools differently from
// another. Sections may split the catalog; they may not resequence it.
test("no section reorders the tools relative to the catalog", () => {
  const catalog = ALL_TOOLS.map((tool) => tool.id);
  for (const section of TOOL_SECTIONS) {
    const declared = [...section.toolIds];
    const catalogOrder = catalog.filter((id) => declared.includes(id));
    assert.deepEqual(
      declared,
      catalogOrder,
      `${section.id} presents its tools in a different order than lib/tools.ts`,
    );
  }
});

test("the catalog leads with the order a PPL uses the tools in", () => {
  const pst = WORKSPACE_TOOLS.filter((tool) => tool.audience === "pst").map(
    (tool) => tool.id,
  );
  // Librarian trails the four judging tools: it answers the question that comes
  // before any of them, but it reads a stored library rather than a document, so it
  // is presented as its own group rather than a fifth card in that band.
  assert.deepEqual(pst, [
    "inspector",
    "scout",
    "aligner",
    "expert",
    "librarian",
  ]);
});

test("a section renders the tools it declares, in that order", () => {
  const pst = TOOL_SECTIONS.find((section) => section.id === "pst-workflows");
  assert.ok(pst);
  assert.deepEqual(
    sectionTools(pst, () => true).map((tool) => tool.id),
    ["inspector", "scout", "aligner", "expert"],
  );
});

test("a section drops the tools an audience filter excludes without resorting", () => {
  const pst = TOOL_SECTIONS.find((section) => section.id === "pst-workflows");
  assert.ok(pst);
  assert.deepEqual(
    sectionTools(pst, (tool) => tool.availability === "available").map(
      (tool) => tool.id,
    ),
    ["inspector", "scout"],
  );
});

test("no external tool is defined twice or shares an id with a workspace tool", () => {
  const ids = [...WORKSPACE_TOOLS, ...EXTERNAL_TOOLS].map((tool) => tool.id);
  assert.equal(new Set(ids).size, ids.length);
});
