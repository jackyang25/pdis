import { defaultUrlTransform } from "react-markdown";

/**
 * What a citation in an assistant answer points at.
 *
 * Every reference the agent makes is written as a markdown link, so the renderer
 * never has to recognise one in prose — markdown already parses links, and the
 * scheme says what kind it is. A pattern hunting for block IDs in free text would
 * have to guess at intent and would turn any lookalike into a dead control.
 *
 * One rule decides all three kinds: a citation is a citation only if it resolves.
 * A block resolves against the passages the browser holds; a URL resolves against
 * the URLs the answer was grounded in; an unknown scheme resolves against nothing.
 * Anything that does not resolve renders as plain text, keeping the sentence and
 * losing only the control.
 *
 * The URL check exists because a model can compose a plausible one. Nothing about
 * `https://pubmed.ncbi.nlm.nih.gov/31234567` distinguishes a source that was
 * retrieved from one that was invented, and a reader who clicks a fabricated
 * citation and lands on a 404 has been told something false about the evidence.
 * The answer's own material is the only authority on which URLs are real.
 */

export type Citation =
  | { kind: "block"; blockId: string }
  | { kind: "external"; href: string }
  | { kind: "plain" };

/**
 * The URLs an answer is allowed to link.
 *
 * Passed in rather than read here: the material differs per conversation, and a
 * default would have to be either every URL or none. Required rather than
 * optional, so a caller cannot fail open by forgetting it.
 */
export type CitationSources = { urls: ReadonlySet<string> };

/** Written by the agent as `[text](block:document/b-0012)`. */
const BLOCK_SCHEME = "block:";

export function parseCitation(
  href: string | undefined,
  sources: CitationSources,
): Citation {
  if (!href) return { kind: "plain" };
  if (href.startsWith(BLOCK_SCHEME)) {
    // Percent-decoded, because a URL is what arrives here: the renderer encodes
    // spaces, and a block ID carries the document name. `DRAFT AIV iTPP v1
    // 13July2016/b-0010` reached this function as `DRAFT%20AIV%20...`, matched no
    // block, and every citation rendered as plain text.
    const blockId = decodeBlockId(href.slice(BLOCK_SCHEME.length).trim());
    // A scheme with nothing after it cites nothing; render the text plainly
    // rather than a control that resolves to no passage.
    return blockId ? { kind: "block", blockId } : { kind: "plain" };
  }
  if (/^https?:\/\//i.test(href)) {
    // A URL the material never contained is not a citation, whatever it looks
    // like. Rendered as text so the claim survives and only the false promise of
    // a checkable source is withdrawn.
    return sources.urls.has(canonicalUrl(href))
      ? { kind: "external", href }
      : { kind: "plain" };
  }
  return { kind: "plain" };
}

/**
 * Collects every URL the given material contains.
 *
 * Variadic because the material arrives in pieces — the analysis under
 * discussion, and the product documentation whose links are part of the product
 * rather than of any one result. Composing them here keeps one answer to what is
 * citable, even though the pieces are supplied by the caller: this module cannot
 * import the documentation itself, which is JSON loaded the way the bundler
 * allows and plain node does not.
 *
 * Walks the whole tree rather than reading named fields. A URL is a URL wherever
 * it sits, and the alternative is a list of paths that silently stops covering a
 * result shape the moment one gains a field.
 */
export function citationSources(...material: unknown[]): CitationSources {
  const urls = new Set<string>();
  const visit = (value: unknown) => {
    if (typeof value === "string") {
      if (/^https?:\/\//i.test(value)) urls.add(canonicalUrl(value));
      return;
    }
    if (Array.isArray(value)) {
      value.forEach(visit);
      return;
    }
    if (value && typeof value === "object") Object.values(value).forEach(visit);
  };
  material.forEach(visit);
  return { urls };
}

/**
 * One spelling per address, so formatting differences do not read as forgery.
 *
 * Forgiving about case and a trailing slash, which carry no meaning, and strict
 * about everything else. Deliberately not host-only matching: a model that had
 * seen one PubMed record could then link any other, which is exactly the failure
 * this is here to catch.
 */
function canonicalUrl(raw: string): string {
  try {
    const url = new URL(raw);
    url.protocol = url.protocol.toLowerCase();
    url.hostname = url.hostname.toLowerCase();
    if (url.pathname.length > 1 && url.pathname.endsWith("/")) {
      url.pathname = url.pathname.slice(0, -1);
    }
    return url.href;
  } catch {
    // Not parseable, so it cannot be matched against anything. Returned as-is:
    // an unparseable URL will simply not be found in the set.
    return raw;
  }
}

/**
 * Which URLs survive into the rendered answer.
 *
 * `react-markdown` blanks any scheme outside http/https/mailto/tel, so model
 * output cannot smuggle `javascript:`. That default also blanked `block:`, the
 * scheme this app defines, which is why a correctly written citation rendered as
 * plain text with nothing to click.
 *
 * The allowlist is kept, not replaced: only `block:` is added, and it resolves to
 * a passage already held in the browser rather than navigating anywhere.
 */
export function transformCitationUrl(url: string): string {
  if (url.startsWith(BLOCK_SCHEME)) return url;
  return defaultUrlTransform(url);
}

/**
 * The block ID inside a citation URL.
 *
 * Malformed encoding keeps the raw text rather than throwing: a citation that
 * cannot be decoded should cost its own link, not the answer around it.
 */
function decodeBlockId(raw: string): string {
  try {
    return decodeURIComponent(raw);
  } catch {
    return raw;
  }
}
