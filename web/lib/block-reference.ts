export function compactBlockId(blockId: string): string {
  const compact = blockId.split("/").filter(Boolean).at(-1);
  return compact || "Unavailable";
}

export function blockReferenceLabel(blockId: string): string {
  return `Source block ID ${blockId}`;
}

/**
 * The accessible name for the document-trace trigger.
 *
 * Leads with the visible label. WCAG 2.5.3 asks that the accessible name contain the text a
 * sighted reader sees, so renaming the button to "In document" without this would leave
 * voice control asking for "view source" on a control that no longer says it.
 */
export function sourcePassageAriaLabel(count: number): string {
  return `In document: ${count} source ${count === 1 ? "passage" : "passages"}`;
}

/**
 * The block a citation refers to, or null.
 *
 * Exact match only. A tolerant version briefly accepted a unique trailing
 * segment, on the belief that the model shortened destinations — it did not.
 * It wrote the full ID and the renderer percent-encoded it, which is fixed where
 * the URL is read. Forgiving a shorter form was answering a question nobody
 * asked, and it masked whether the real form worked.
 */
export function resolveBlock<TBlock extends { id: string }>(
  blocks: TBlock[],
  blockId: string,
): TBlock | null {
  const wanted = blockId.trim();
  if (!wanted) return null;
  return blocks.find((item) => item.id === wanted) ?? null;
}
