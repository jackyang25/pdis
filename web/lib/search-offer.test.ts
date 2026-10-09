import assert from "node:assert/strict";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { loadComponent } from "../test-support/load-component.ts";
import { readSearchHandoff, readSearchOffer, searcherHref } from "./search-offer.ts";

const { SearchOfferCard } = loadComponent(
  fileURLToPath(new URL("../components/assistant/search-offer-card.tsx", import.meta.url)),
);

test("an offer opens Searcher with its fields, and Searcher reads them back", () => {
  const offer = readSearchOffer({ tool: "searcher", fields: { query: "RSV efficacy", region: "LMICs", stray: "x" } });
  assert.ok(offer);
  const href = searcherHref(offer);
  assert.equal(href, "/searcher?query=RSV+efficacy&region=LMICs");
  assert.deepEqual(readSearchHandoff(href.split("?")[1]), {
    fields: { query: "RSV efficacy", region: "LMICs" },
    sources: [],
    entities: [],
  });
});

test("an offer's sources and entities travel to Searcher and back", () => {
  const offer = readSearchOffer({
    tool: "searcher",
    fields: { query: "BRAF inhibitor resistance" },
    sources: [{ key: "pubmed", label: "PubMed" }, { key: 7 }],
    entities: [{ name: "BRAF", entity_type: "gene" }, { name: "x" }],
  });
  assert.ok(offer);
  assert.deepEqual(offer.sources, [{ key: "pubmed", label: "PubMed" }]);
  const href = searcherHref(offer);
  assert.equal(href, "/searcher?query=BRAF+inhibitor+resistance&sources=pubmed&entity=BRAF%3Agene");
  assert.deepEqual(readSearchHandoff(href.split("?")[1]), {
    fields: { query: "BRAF inhibitor resistance" },
    sources: ["pubmed"],
    entities: [{ name: "BRAF", entity_type: "gene" }],
  });
  // A name may itself hold a colon; the type never does.
  assert.deepEqual(readSearchHandoff("query=q&entity=HLA-B%2A57%3A01%3Agene&entity=nocolon").entities, [
    { name: "HLA-B*57:01", entity_type: "gene" },
  ]);
});

test("an event that is not a searcher offer with a query opens nothing", () => {
  assert.equal(readSearchOffer({ tool: "scout", fields: { query: "q" } }), null);
  assert.equal(readSearchOffer({ tool: "searcher", fields: { condition: "RSV" } }), null);
  assert.equal(readSearchOffer("searcher"), null);
});

test("the card shows what would be searched and only links to Searcher", () => {
  const offer = readSearchOffer({ tool: "searcher", fields: { query: "RSV efficacy", condition: "RSV" } });
  const html = renderToStaticMarkup(createElement(SearchOfferCard, { offer }));
  assert.match(html, /aria-label="Suggested search"/);
  assert.match(html, />RSV efficacy</);
  assert.match(html, /Condition<\/span>RSV/);
  assert.match(html, /href="\/searcher\?query=RSV\+efficacy&amp;condition=RSV"/);
  assert.doesNotMatch(html, /Sources?<\/span>/);
  // Nothing on the card runs: its one control is a link to the page where the reader does.
  assert.doesNotMatch(html, /<button\b|onClick/);
});

test("the card names the sources and subjects the search is scoped to", () => {
  const offer = readSearchOffer({
    tool: "searcher",
    fields: { query: "BRAF resistance" },
    sources: [{ key: "pubmed", label: "PubMed" }, { key: "chembl", label: "ChEMBL" }],
    entities: [{ name: "BRAF", entity_type: "gene" }],
  });
  const html = renderToStaticMarkup(createElement(SearchOfferCard, { offer }));
  assert.match(html, /Gene<\/span>BRAF/);
  assert.match(html, /Sources<\/span>PubMed, ChEMBL/);
  assert.doesNotMatch(html, /<button\b|onClick/);
});
