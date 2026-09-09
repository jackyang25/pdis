import type { ContentBlock } from "./api";

export type DocumentBlockBoundary = { kind: "page" | "slide"; number: number; label: string };

/** Only declared, unambiguous physical boundaries qualify for grouping. */
export function documentBlockBoundary(block: ContentBlock): DocumentBlockBoundary | null {
  const { page, slide } = block.structural_meta;
  const valid = (value: unknown): value is number =>
    typeof value === "number" && Number.isInteger(value) && value > 0;
  if (valid(page) && valid(slide)) return null;
  if (valid(page)) return { kind: "page", number: page, label: `Page ${page}` };
  if (valid(slide)) return { kind: "slide", number: slide, label: `Slide ${slide}` };
  return null;
}

/** Locations are source metadata, never inferred headings or text snippets. */
export function documentBlockLocationLabel(block: ContentBlock): string {
  return documentBlockBoundary(block)?.label || block.section_label || block.heading_stack.at(-1) || "";
}

/** A parser records limitations; consumers translate, never re-diagnose a file. */
export function documentExtractionWarnings(blocks: readonly ContentBlock[]): {
  code: string; documentIds: string[];
}[] {
  const documentsByCode = new Map<string, Set<string>>();
  for (const block of blocks) {
    const warnings = block.structural_meta.extraction_warnings;
    if (!Array.isArray(warnings)) continue;
    for (const code of warnings) {
      if (typeof code !== "string") continue;
      if (!documentsByCode.has(code)) documentsByCode.set(code, new Set());
      documentsByCode.get(code)!.add(block.doc_id);
    }
  }
  return [...documentsByCode].map(([code, documents]) => ({ code, documentIds: [...documents] }));
}
