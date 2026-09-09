import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { loadComponent } from "../test-support/load-component.ts";
import type { ContentBlock } from "./api.ts";

const { DocumentTraceViewer } = loadComponent(fileURLToPath(new URL("../components/document-trace-viewer.tsx", import.meta.url)));

function block(id: string, meta = {}): ContentBlock {
  return { id, doc_id: "document", ordinal: 1, content: `Source text ${id}`,
    block_type: "paragraph", heading_stack: [], section_label: null,
    structural_meta: meta, style_hint: {} };
}

function render(blocks: ContentBlock[]) {
  return renderToStaticMarkup(React.createElement(DocumentTraceViewer, {
    blocks: blocks.map((block, index) => ({ ...block, ordinal: index + 1 })),
    annotations: [{ id: "finding", kind: "finding", layerLabel: "Finding", title: "A finding", summary: "Summary",
      blockIds: [blocks.at(-1)!.id], spans: [], sourceRef: {} }],
    layers: [{ value: "finding", label: "Findings" }], renderInspector: () => null,
  }));
}

test("the real viewer renders separate PDF surfaces with one label per page and unchanged block targets", () => {
  const html = render([block("one", { page: 1 }), block("two", { page: 1 }), block("three", { page: 2 })]);
  assert.equal(html.match(/data-trace-surface=/g)?.length, 2);
  assert.equal(html.match(/>Page 1</g)?.length, 1);
  assert.equal(html.match(/>Page 2</g)?.length, 1);
  for (const id of ["one", "two", "three"]) assert.match(html, new RegExp(`data-block-id="${id}"`));
  assert.match(html, /source passage three/);
  assert.ok(html.indexOf("Source text one") < html.indexOf("Source text two"));
  assert.ok(html.indexOf("Source text two") < html.indexOf("Source text three"));
});

test("the real viewer labels slides without pretending extracted content is a slide canvas", () => {
  const html = render([block("one", { slide: 1 }), block("two", { slide: 2 })]);
  assert.equal(html.match(/data-trace-surface=/g)?.length, 2);
  assert.match(html, />Slide 1</);
  assert.match(html, />Slide 2</);
  assert.doesNotMatch(html, /aspect-video|aspect-ratio|>Page /);
});

test("Word stays on one continuous unlabeled surface", () => {
  const html = render([block("one"), block("two")]);
  assert.equal(html.match(/data-trace-surface=/g)?.length, 1);
  assert.doesNotMatch(html, />Page \d|>Slide \d/);
  assert.match(html, /Source text one/);
  assert.match(html, /Source text two/);
});
