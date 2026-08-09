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
    const blockId = href.slice(BLOCK_SCHEME.length).trim();
    // A scheme with nothing after it cites nothing; render the text plainly
    // rather than a control that resolves to no passage.
    return blockId ? { kind: "block", blockId } : { kind: "plain" };
  }
  if (/^https?:\/\//i.test(href)) return { kind: "external", href };
  return { kind: "plain" };
}
