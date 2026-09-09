import type { ContentBlock } from "./api";
import { documentBlockBoundary, type DocumentBlockBoundary } from "./document-extraction.ts";

export type DocumentTraceSurface<T> = {
  key: string;
  boundary: DocumentBlockBoundary | null;
  blocks: T[];
};

/**
 * Presentation-only runs of adjacent blocks. Never sort, fill a missing page,
 * carry a boundary forward, or rebuild a trace block and its citation identity.
 */
export function groupDocumentTraceSurfaces<T extends { block: ContentBlock }>(
  blocks: readonly T[],
): DocumentTraceSurface<T>[] {
  const surfaces: DocumentTraceSurface<T>[] = [];
  for (const item of blocks) {
    const boundary = documentBlockBoundary(item.block);
    const previous = surfaces.at(-1);
    if (previous
      && previous.blocks[0].block.doc_id === item.block.doc_id
      && previous.boundary?.kind === boundary?.kind
      && previous.boundary?.number === boundary?.number) {
      previous.blocks.push(item);
    } else {
      surfaces.push({ key: item.block.id, boundary, blocks: [item] });
    }
  }
  return surfaces;
}
