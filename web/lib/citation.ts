import { defaultUrlTransform } from "react-markdown";

/**
 * What a citation in an assistant answer points at.
 *
 * Every reference the agent makes is written as a markdown link, so the renderer
 * never has to recognise one in prose — markdown already parses links, and the
 * scheme says what kind it is. A pattern hunting for block IDs in free text would
 * have to guess at intent and would turn any lookalike into a dead control.
 *
 * An unknown scheme stays an ordinary link. That is what makes adding a kind
 * later safe: nothing breaks in the meantime, it simply is not special yet.
 */

export type Citation =
  | { kind: "block"; blockId: string }
  | { kind: "external"; href: string }
  | { kind: "plain" };

/** Written by the agent as `[text](block:document/b-0012)`. */
const BLOCK_SCHEME = "block:";

export function parseCitation(href: string | undefined): Citation {
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
  if (/^https?:\/\//i.test(href)) return { kind: "external", href };
  return { kind: "plain" };
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
