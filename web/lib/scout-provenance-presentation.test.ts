import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { loadComponent } from "../test-support/load-component.ts";

// Keep the source content real; only bypass the browser-only portal.
const Surface = ({ children }: { children: React.ReactNode }) => React.createElement("div", null, children);
const { EvidenceProvenance } = loadComponent(
  fileURLToPath(new URL("../components/evidence-provenance.tsx", import.meta.url)),
  { "@/components/ui/popover": { Popover: Surface, PopoverTrigger: Surface, PopoverContent: Surface } },
);

test("source previews retain the full excerpt and put retrieval queries in a closed disclosure", () => {
  const excerpt = "Retained source text. ".repeat(30) + "Final retained sentence.";
  const html = renderToStaticMarkup(React.createElement(EvidenceProvenance, { insight: {
    supporting_findings: [{ url: "https://example.org/paper", title: "A paper", source: "pubmed", excerpt,
      retrieval_paths: [{ lane: "pubmed", query: "exact query α", connector: "pubmed", operation: "search" }],
    }], query_tracks: ["general"],
  } }));
  assert.match(html, /Final retained sentence\./);
  assert.match(html, /Read full excerpt/);
  assert.match(html, /<details[^>]*><summary[^>]*>.*Search queries/s);
  assert.doesNotMatch(html, /<details[^>]* open/);
  assert.match(html, /exact query α/);
  assert.match(html, /aria-label="Close sources"/);
  assert.match(html, /href="https:\/\/example.org\/paper"/);
});

test("retrieved excerpts render emphasis and safe links without executing embedded content", () => {
  const html = renderToStaticMarkup(React.createElement(EvidenceProvenance, { insight: {
    supporting_findings: [{ url: "https://example.org/paper", title: "A paper", source: "web",
      excerpt: '**June 2024** [WHO](https://www.who.int/report) [unsafe](javascript:alert%281%29) <script>alert(1)</script>',
    }], query_tracks: [],
  } }));
  assert.match(html, /<strong>June 2024<\/strong>/);
  assert.match(html, /href="https:\/\/www.who.int\/report"/);
  assert.doesNotMatch(html, /href="javascript:|<script>/);
});

test("search failures are process warnings, not model-authored readings", () => {
  const { FieldSearches } = loadComponent(
    fileURLToPath(new URL("../components/field-searches.tsx", import.meta.url)),
    { "@/components/ui/popover": { Popover: Surface, PopoverTrigger: Surface, PopoverContent: Surface } },
  );
  const html = renderToStaticMarkup(React.createElement(FieldSearches, {
    attributeRef: "stage", result: { search_plan: [{ attribute_ref: "stage", lane: "semantic_scholar",
      query: "exact query", status: "failed", error: "RuntimeError: connection refused", finding_count: 0 } ] },
  }));
  assert.match(html, /RuntimeError: connection refused/);
  assert.match(html, /lucide-triangle-alert/);
  assert.doesNotMatch(html, /fill-current/);
});

test("document excerpts remain literal and retain their full text when collapsed", () => {
  const { Quoted } = loadComponent(fileURLToPath(new URL("../components/ui/evidence-text.tsx", import.meta.url)));
  const text = "Literal **wording**. ".repeat(40) + "Final source sentence.";
  const html = renderToStaticMarkup(React.createElement(Quoted, { collapsible: true }, text));
  assert.match(html, /Literal \*\*wording\*\*/);
  assert.match(html, /Final source sentence\./);
  assert.match(html, /aria-expanded="false"/);
  assert.match(html, /Read full excerpt/);
});
