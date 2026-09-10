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
      { id: "b-1", content: "First risk: delivery timing.", section_label: "Project risks", heading_stack: [], structural_meta: {}, block_type: "paragraph", ordinal: 0 },
      { id: "b-2", content: "Second risk: manufacturing capacity.", section_label: "Project risks", heading_stack: [], structural_meta: {}, block_type: "paragraph", ordinal: 1 },
    ],
  }, React.createElement(DocumentSourceTrace, { blockIds: ["b-1", "b-2"] })));
  assert.match(html, /Second risk: manufacturing capacity/);
  assert.match(html, /aria-current="true"/);
  assert.match(html, /aria-label="Close source passages"/);
});

test("missing retained passages remain selectable without invented preview text", () => {
  const html = renderToStaticMarkup(React.createElement(DocumentSourceTrace, { blockIds: ["missing-1", "missing-2"] }));
  assert.match(html, /Source passage unavailable/);
  assert.match(html, /Passage 2/);
  assert.doesNotMatch(html, /View in document/);
});
