import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { loadComponent } from "../test-support/load-component.ts";

const { Inspector } = loadComponent(fileURLToPath(new URL("../components/scout-evidence-map.tsx", import.meta.url)), {}, ["Inspector"]);

test("map inspector retains every retrieval query in an openable disclosure", () => {
  const html = renderToStaticMarkup(React.createElement(Inspector, { node: {
    id: "source:1", kind: "source", eyebrow: "Cited source", title: "Source title",
    summary: "Retained excerpt", summaryMode: "quoted", queries: ["first query", "second query", "第三个查询"],
  } }));
  assert.match(html, /second query/);
  assert.match(html, /第三个查询/);
  assert.match(html, /<summary[^>]*>[\s\S]*?Retrieval queries/);
  assert.doesNotMatch(html, /further retrieval path/);
});

test("map source excerpts render Markdown while document quotations stay literal", () => {
  const node = { id: "source:1", kind: "source", eyebrow: "Cited source", title: "Source", summary: "A **retained** excerpt", summaryMode: "quoted" };
  const source = renderToStaticMarkup(React.createElement(Inspector, { node }));
  const document = renderToStaticMarkup(React.createElement(Inspector, { node: { ...node, kind: "document" } }));
  assert.match(source, /<strong>retained<\/strong>/);
  assert.match(document, /\*\*retained\*\*/);
});
