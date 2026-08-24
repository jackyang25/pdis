/**
 * One citation, all the way through the renderer to a resolved block.
 *
 * Every layer of this passed on its own while citations rendered as dead text
 * for a day: the agent emitted a correct link, the transport delivered it, the
 * parser read the scheme, the resolver matched IDs. The failures were both in
 * the seams — a URL sanitiser blanking an unknown scheme, then the renderer
 * percent-encoding the spaces in a document name.
 *
 * Layer tests cannot see a seam. This one renders the real pipeline.
 */

import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import {
  citationSources,
  parseCitation,
  transformCitationUrl,
} from "./citation.ts";
import { resolveBlock } from "./block-reference.ts";

const DOC = "DRAFT AIV iTPP v1 13July2016";

/** Render one answer the way `ask.tsx` does, reporting what each link became. */
function render(
  markdown: string,
  blocks: { id: string }[],
  /** The material the answer was grounded in; only URL citations consult it. */
  material: unknown = {},
) {
  const sources = citationSources(material);
  const seen: { kind: string; resolved: string | null }[] = [];
  renderToStaticMarkup(
    React.createElement(ReactMarkdown, {
      remarkPlugins: [remarkGfm],
      urlTransform: transformCitationUrl,
      components: {
        a: ({ href }: { href?: string }) => {
          const citation = parseCitation(href, sources);
          seen.push({
            kind: citation.kind,
            resolved:
              citation.kind === "block"
                ? resolveBlock(blocks, citation.blockId)?.id ?? null
                : null,
          });
          return null;
        },
      },
      children: markdown,
    } as never),
  );
  return seen;
}

test("a cited passage reaches the block it names", () => {
  const blocks = [{ id: `${DOC}/b-0010` }];
  assert.deepEqual(
    render(`See [Instructions for Use](<block:${DOC}/b-0010>).`, blocks),
    [{ kind: "block", resolved: `${DOC}/b-0010` }],
  );
});

test("a document name with spaces survives the round trip", () => {
  // The renderer percent-encodes the URL; the ID has to arrive decoded or it
  // matches nothing. This is the failure that looked like every other failure.
  const blocks = [{ id: `${DOC}/b-0080` }];
  const [seen] = render(`[Executive Summary](<block:${DOC}/b-0080>)`, blocks);
  assert.equal(seen.resolved, `${DOC}/b-0080`);
});

test("an evidence link the material contains is still an ordinary link", () => {
  assert.deepEqual(
    render("[a paper](https://example.org/p)", [], { url: "https://example.org/p" }),
    [{ kind: "external", resolved: null }],
  );
});

test("an invented URL renders as text on the real render path", () => {
  // Asserted here and not only on the parser: this is the reported failure, and
  // the citation work has already been through several rounds where each layer
  // passed alone while the rendered answer was still wrong.
  assert.deepEqual(
    render("[a paper](https://example.org/invented)", [], { url: "https://example.org/p" }),
    [{ kind: "plain", resolved: null }],
  );
});

test("a fabricated link keeps its sentence", () => {
  // What the reader is left with. Losing the paragraph would be a worse failure
  // than the bad link.
  const html = renderToStaticMarkup(
    React.createElement(ReactMarkdown, {
      remarkPlugins: [remarkGfm],
      urlTransform: transformCitationUrl,
      components: {
        a: ({ children, href }: { children?: React.ReactNode; href?: string }) =>
          parseCitation(href, citationSources({})).kind === "external"
            ? React.createElement("a", { href }, children)
            : React.createElement(React.Fragment, null, children),
      },
      children: "Efficacy was [61% in the pivotal trial](https://example.org/made-up).",
    }),
  );
  assert.match(html, /61% in the pivotal trial/);
  assert.doesNotMatch(html, /<a/);
});

test("a script URL never becomes a citation", () => {
  // The sanitiser is widened for one internal scheme, so the case it exists for
  // is asserted on the real render path rather than only on the helper.
  assert.deepEqual(render("[click](javascript:alert(1))", []), [
    { kind: "plain", resolved: null },
  ]);
});

test("a block the workspace does not hold resolves to nothing", () => {
  const [seen] = render(`[Gone](<block:${DOC}/b-9999>)`, [{ id: `${DOC}/b-0010` }]);
  assert.equal(seen.kind, "block");
  assert.equal(seen.resolved, null);
});
