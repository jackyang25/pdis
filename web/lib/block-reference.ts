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
