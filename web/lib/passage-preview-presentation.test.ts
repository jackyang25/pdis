import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { loadComponent } from "../test-support/load-component.ts";

// The portal normally mounts only in a browser; retain the real preview content.
const Surface = ({ children }: { children: React.ReactNode }) => React.createElement("div", null, children);
const { DocumentSourceProvider, DocumentSourceTrace } = loadComponent(
  fileURLToPath(new URL("../components/document-source-trace.tsx", import.meta.url)),
  { "@/components/ui/popover": { Popover: Surface, PopoverTrigger: Surface, PopoverContent: Surface } },
);

test("passage navigation distinguishes repeated headings using retained text and exposes selection", () => {
  const html = renderToStaticMarkup(React.createElement(DocumentSourceProvider, {
    blocks: [
      { id: "b-1", doc_id: "Risk register", content: "First risk: delivery timing.", section_label: "Project risks", heading_stack: [], structural_meta: {}, block_type: "paragraph", ordinal: 0 },
      { id: "b-2", doc_id: "Risk register", content: "Second risk: manufacturing capacity.", section_label: "Project risks", heading_stack: [], structural_meta: {}, block_type: "paragraph", ordinal: 1 },
    ],
  }, React.createElement(DocumentSourceTrace, { blockIds: ["b-1", "b-2"] })));
  assert.match(html, /Second risk: manufacturing capacity/);
  assert.match(html, /aria-current="true"/);
  assert.match(html, /aria-label="Close source passages"/);
  // One document: named once, as the panel's title, and not again on every passage.
  assert.match(html, /<h3[^>]*>Risk register<\/h3>/);
  assert.doesNotMatch(html, /Uploaded document/);
  assert.equal(html.match(/>Risk register</g)?.length, 1);
});

test("passages spanning documents each name theirs, and a visual is named for what it is", () => {
  const html = renderToStaticMarkup(React.createElement(DocumentSourceProvider, {
    blocks: [
      { id: "Plan/b-1", doc_id: "Plan", source_format: "pdf", content: "Dose rationale.", heading_stack: [], structural_meta: { page: 6 }, block_type: "paragraph", ordinal: 0 },
      { id: "Deck/b-9", doc_id: "Deck", source_format: "pptx", content: "[image]", heading_stack: [], structural_meta: { slide: 34, visual_scope: "full_slide" }, block_type: "image", ordinal: 8 },
    ],
  }, React.createElement(DocumentSourceTrace, { blockIds: ["Plan/b-1", "Deck/b-9"] })));
  assert.match(html, /<h3[^>]*>Uploaded documents<\/h3>/);
  assert.match(html, />PDF<[\s\S]*?>Plan<[\s\S]*?>Page 6</);
  assert.match(html, />PPTX<[\s\S]*?>Deck<[\s\S]*?>Slide 34</);
  assert.match(html, /Slide visual/);
  assert.doesNotMatch(html, /\[image\]/);
});

test("missing retained passages remain selectable without invented preview text", () => {
  const html = renderToStaticMarkup(React.createElement(DocumentSourceTrace, { blockIds: ["missing-1", "missing-2"] }));
  assert.match(html, /Source passage unavailable/);
  assert.match(html, /Passage 2/);
  assert.doesNotMatch(html, /View in document/);
});

test("a closed source trigger reads no passage until it is opened", () => {
  // A result page renders one trigger per finding. Each used to index every block of the
  // run and mark its cited text on every render, open or not, which on a large document
  // was most of the cost of a keystroke in a search box.
  let marked = 0;
  const cited = loadComponent(fileURLToPath(new URL("../lib/cited-text.ts", import.meta.url)));
  const { DocumentSourceProvider: Provider, DocumentSourceTrace: Trace } = loadComponent(
    fileURLToPath(new URL("../components/document-source-trace.tsx", import.meta.url)),
    { "@/lib/cited-text": { ...cited, markCitedText: (...args: unknown[]) => {
      marked += 1;
      return cited.markCitedText(...args);
    } } },
  );
  const html = renderToStaticMarkup(React.createElement(Provider, {
    blocks: [{ id: "b-1", doc_id: "Plan", content: "Dose rationale.", heading_stack: [], structural_meta: {}, block_type: "paragraph", ordinal: 0 }],
  }, React.createElement(Trace, { blockIds: ["b-1"] })));
  assert.match(html, /In document/);
  assert.equal(marked, 0);
});
