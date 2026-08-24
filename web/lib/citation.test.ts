/**
 * Every reference in an answer is a markdown link; the scheme says what it is.
 *
 * The alternative was hunting for block IDs in prose, which would have to guess
 * at intent and would turn any lookalike into a control that opens nothing.
 * These pin the two ends: a declared citation is recognised, and anything else
 * stays text rather than becoming a broken control.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";

import {
  citationSources,
  parseCitation,
  transformCitationUrl,
} from "./citation.ts";

/**
 * Sources for the cases that are not about URLs at all.
 *
 * Empty on purpose: a block citation resolves against the passages the browser
 * holds, not against this set, so nothing here should change its outcome.
 */
const NO_URLS = citationSources();

const REPO = path.resolve(import.meta.dirname, "..", "..");
const AGENT = path.join(REPO, "services", "assistant", "agent.py");

test("the scheme matches the one the agent is told to write", () => {
  const prompt = readFileSync(AGENT, "utf8");
  assert.match(
    prompt,
    /\(<block:EXACT-BLOCK-ID>\)/,
    "agent.py no longer instructs the block: scheme this file parses",
  );
});

test("the agent is told to bracket the destination", () => {
  // A block ID carries the document name, and a name with spaces is not a valid
  // link destination unbracketed: markdown renders the raw syntax as text, which
  // is exactly what a reader saw. Brackets are stripped before the href reaches
  // parseCitation, so nothing downstream changes.
  const prompt = readFileSync(AGENT, "utf8");
  assert.match(prompt, /in angle brackets, never shortened/);
});

test("there are two citation kinds, both openable", () => {
  // A third kind printed a raw JSON path at the reader. Every citation now
  // resolves to something clickable, or it is not a citation.
  const prompt = readFileSync(AGENT, "utf8");
  assert.match(prompt, /Never print a result path/);
});

test("the label and the destination are told apart", () => {
  // Why the destination broke: repeating a full block ID through a table is
  // unreadable, so the model shortened both. A link already separates the two,
  // and saying so lets it keep the answer readable without breaking the target.
  const prompt = readFileSync(AGENT, "utf8");
  assert.match(prompt, /visible text is for the reader/);
  assert.match(prompt, /destination is what opens/);
});

test("a bracketed destination arrives here already unwrapped", () => {
  // remark strips the brackets, so the parser sees the same href either way.
  assert.deepEqual(parseCitation("block:DRAFT AIV iTPP v1 13July2016/b-0080", NO_URLS), {
    kind: "block",
    blockId: "DRAFT AIV iTPP v1 13July2016/b-0080",
  });
});

test("a cited passage is recognised", () => {
  assert.deepEqual(parseCitation("block:document/b-0012", NO_URLS), {
    kind: "block",
    blockId: "document/b-0012",
  });
});

test("an evidence link the material contains stays an external link", () => {
  const sources = citationSources({ url: "https://example.org/paper" });
  assert.deepEqual(parseCitation("https://example.org/paper", sources), {
    kind: "external",
    href: "https://example.org/paper",
  });
});

test("a scheme citing nothing is text, not an empty control", () => {
  assert.deepEqual(parseCitation("block:", NO_URLS), { kind: "plain" });
  assert.deepEqual(parseCitation("block:   ", NO_URLS), { kind: "plain" });
});

test("an unknown scheme degrades to text rather than breaking", () => {
  // What makes adding a kind later safe: until it is handled it is simply not
  // special, and nothing renders wrong in the meantime.
  assert.deepEqual(parseCitation("path:matches[3]", NO_URLS), { kind: "plain" });
  assert.deepEqual(parseCitation("javascript:alert(1)", NO_URLS), { kind: "plain" });
  assert.deepEqual(parseCitation(undefined, NO_URLS), { kind: "plain" });
});

test("only http and https are followed", () => {
  // A link is opened in a new tab, so anything that is not a web address is
  // not made clickable at all.
  assert.equal(parseCitation("ftp://example.org/x", NO_URLS).kind, "plain");
  assert.equal(parseCitation("//example.org", NO_URLS).kind, "plain");
});

test("the block scheme survives the renderer's URL sanitiser", () => {
  // The failure every other layer hid: react-markdown blanks any scheme outside
  // http/https/mailto/tel, so `block:` arrived as "" and parseCitation correctly
  // saw nothing to open. API, bundle, parser and resolver all checked out alone.
  assert.equal(
    transformCitationUrl("block:DRAFT AIV iTPP v1 13July2016/b-0010"),
    "block:DRAFT AIV iTPP v1 13July2016/b-0010",
  );
});

test("ordinary links still pass", () => {
  assert.equal(
    transformCitationUrl("https://example.org/paper"),
    "https://example.org/paper",
  );
});

test("the sanitiser is extended, not replaced", () => {
  // The reason it exists: model output must not be able to smuggle a script URL.
  assert.equal(transformCitationUrl("javascript:alert(1)"), "");
  assert.equal(transformCitationUrl("data:text/html,<script>"), "");
  assert.equal(transformCitationUrl("vbscript:msgbox"), "");
});

test("a percent-encoded block id is decoded back to the real one", () => {
  // What the renderer actually delivers: it encodes spaces, and a block ID
  // carries the document name. Undecoded, this matched no block and every
  // citation fell back to plain text while each layer tested green alone.
  assert.deepEqual(
    parseCitation("block:DRAFT%20AIV%20iTPP%20v1%2013July2016/b-0010", NO_URLS),
    { kind: "block", blockId: "DRAFT AIV iTPP v1 13July2016/b-0010" },
  );
});

test("an unencoded id is unchanged", () => {
  assert.deepEqual(parseCitation("block:document/b-0010", NO_URLS), {
    kind: "block",
    blockId: "document/b-0010",
  });
});

test("malformed encoding costs its own link, not the answer", () => {
  // A stray % is not valid encoding; keep the raw text rather than throwing.
  assert.equal(parseCitation("block:doc%ZZ/b-1", NO_URLS).kind, "block");
});

/**
 * A URL is only a citation if the answer's own material contained it.
 *
 * The reported failure: answers carried links that could not be opened, some of
 * them plausible-looking addresses that had never been retrieved. Nothing about
 * an invented URL distinguishes it from a real one by inspection, so the check
 * has to be against the material rather than against the shape of the string.
 */

test("a URL that appears nowhere in the material is not a link", () => {
  // The fabrication case. It renders as text, so the sentence survives and only
  // the promise that a reader can verify it is withdrawn.
  const sources = citationSources({ url: "https://example.org/real-paper" });
  assert.deepEqual(parseCitation("https://example.org/invented-paper", sources), {
    kind: "plain",
  });
});

test("no material at all means no external links", () => {
  // A conversation with no result has no evidence, so there is nothing an
  // evidence link could be pointing at.
  assert.equal(parseCitation("https://pubmed.ncbi.nlm.nih.gov/31234567", NO_URLS).kind, "plain");
});

test("a URL is found wherever it sits in the material", () => {
  // Walked rather than read from named fields: a result gains fields, and a list
  // of paths would quietly stop covering them while still reporting success.
  const sources = citationSources({
    matches: [
      {
        insight: {
          supporting_findings: [{ url: "https://trials.gov/NCT04000000" }],
        },
      },
    ],
  });
  assert.equal(parseCitation("https://trials.gov/NCT04000000", sources).kind, "external");
});

test("a second source in the same material is also citable", () => {
  const sources = citationSources(
    { url: "https://example.org/a" },
    { docs: [{ href: "https://example.org/b" }] },
  );
  assert.equal(parseCitation("https://example.org/a", sources).kind, "external");
  assert.equal(parseCitation("https://example.org/b", sources).kind, "external");
});

test("knowing one address on a host does not license another", () => {
  // The failure a host-level check would have let through, and the reason this
  // compares whole URLs: one retrieved PubMed record must not vouch for every
  // other PubMed record the model can compose.
  const sources = citationSources({ url: "https://pubmed.ncbi.nlm.nih.gov/31234567" });
  assert.equal(
    parseCitation("https://pubmed.ncbi.nlm.nih.gov/99999999", sources).kind,
    "plain",
  );
});

test("formatting differences do not read as forgery", () => {
  // Case and a trailing slash carry no meaning, and a model that reformats a URL
  // it genuinely read has not invented anything.
  const sources = citationSources({ url: "https://Example.org/Paper/" });
  assert.equal(parseCitation("https://example.org/Paper", sources).kind, "external");
});

test("a path difference is a different document", () => {
  // The other side of the same line: only meaningless differences are forgiven.
  const sources = citationSources({ url: "https://example.org/paper" });
  assert.equal(parseCitation("https://example.org/paper/appendix", sources).kind, "plain");
});

test("a query string is part of the address", () => {
  const sources = citationSources({ url: "https://example.org/search?id=1" });
  assert.equal(parseCitation("https://example.org/search?id=2", sources).kind, "plain");
  assert.equal(parseCitation("https://example.org/search?id=1", sources).kind, "external");
});

test("collecting URLs survives the shapes a result actually contains", () => {
  // Called on whatever the payload holds, which includes nulls and numbers.
  // Throwing here would take down the whole answer, not one link.
  const sources = citationSources(null, undefined, 42, "plain text", {
    a: null,
    b: [undefined, { c: "https://example.org/x" }],
  });
  assert.equal(parseCitation("https://example.org/x", sources).kind, "external");
});

test("a non-URL string is not collected as one", () => {
  const sources = citationSources({ statement: "efficacy above 60%", n: "https" });
  assert.equal(sources.urls.size, 0);
});

test("the agent is told not to write a URL it did not read", () => {
  // Binds the prompt to the renderer above. Because a URL absent from the
  // material is silently demoted to text, an agent that was never told this
  // would keep writing links a reader never sees — a citation that vanishes is
  // no better than one that lies.
  const prompt = readFileSync(AGENT, "utf8");
  assert.match(prompt, /Never write a URL you did not read/);
});

test("the agent is told when not to cite at all", () => {
  // The reported behaviour: citations attached to sentences they did not
  // support, and to the assistant's own explanations. Every other rule in the
  // prompt pushes toward citing, so the restraint has to be stated.
  const prompt = readFileSync(AGENT, "utf8");
  assert.match(prompt, /Cite only where a reader would otherwise/);
  assert.match(prompt, /must support the exact sentence/);
});
