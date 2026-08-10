export function compactBlockId(blockId: string): string {
  const compact = blockId.split("/").filter(Boolean).at(-1);
  return compact || "Unavailable";
}

export function blockReferenceLabel(blockId: string): string {
  return `Source block ID ${blockId}`;
}

export function sourcePassageAriaLabel(count: number): string {
  return `View ${count} source ${count === 1 ? "passage" : "passages"}`;
}

/**
 * The block a citation refers to, or null.
 *
 * Exact first. Failing that, a unique suffix match: a block ID carries the
 * document name, so the full form is long and the model routinely cites the
 * short tail instead. That reference is unambiguous whenever exactly one block
 * ends with it, and resolving it is deterministic rather than a guess.
 *
 * Two documents sharing a tail make the reference genuinely ambiguous, so
 * nothing is resolved and the citation renders as text — the same as a block
 * the workspace does not hold.
 */
export function resolveBlock<TBlock extends { id: string }>(
  blocks: TBlock[],
  blockId: string,
): TBlock | null {
  const wanted = blockId.trim();
  if (!wanted) return null;
  const exact = blocks.find((item) => item.id === wanted);
  if (exact) return exact;
  const suffix = blocks.filter(
    (item) => item.id.endsWith(`/${wanted}`) || item.id === wanted,
  );
  return suffix.length === 1 ? suffix[0] : null;
}
