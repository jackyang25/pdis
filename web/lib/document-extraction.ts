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
  const boundary = documentBlockBoundary(block);
  if (boundary) return boundary.label;
  const { document_part_kind: kind, note_id: noteId } = block.structural_meta;
  const labels: Record<string, string> = {
    header: "Header", footer: "Footer", footnote: "Footnote", endnote: "Endnote", textbox: "Text box",
  };
  const part = typeof kind === "string" ? labels[kind] : undefined;
  if (part) {
    const note = (kind === "footnote" || kind === "endnote")
      && (typeof noteId === "string" || typeof noteId === "number") ? ` ${noteId}` : "";
    return `${part}${note}`;
  }
  return block.section_label || block.heading_stack.at(-1) || "";
}

/** A parser records limitations; consumers translate, never re-diagnose a file. */
export function documentExtractionWarnings(blocks: readonly ContentBlock[]): {
  code: string; documentIds: string[]; details?: string[];
}[] {
  const documentsByCode = new Map<string, Set<string>>();
  const visualDetails: { docId: string; label: string }[] = [];
  for (const block of blocks) {
    const warnings = block.structural_meta.extraction_warnings;
    if (!Array.isArray(warnings)) continue;
    for (const code of warnings) {
      if (typeof code !== "string") continue;
      if (!documentsByCode.has(code)) documentsByCode.set(code, new Set());
      documentsByCode.get(code)!.add(block.doc_id);
      if (code === "unsupported_document_visual") {
        const labels: Record<string, string> = {
          drawing: "Drawing", chart: "Chart", diagram: "Diagram", embedded_object: "Embedded object",
        };
        const kind = block.structural_meta.unsupported_visual_kind;
        const type = typeof kind === "string" ? labels[kind] : undefined;
        const location = documentBlockLocationLabel(block)
          || (block.structural_meta.document_part_kind === "body" ? "Document body" : "Location not recorded");
        visualDetails.push({ docId: block.doc_id, label: `${location}: ${type ?? "Visual object"}` });
      }
    }
  }
  return [...documentsByCode].map(([code, documents]) => ({
    code, documentIds: [...documents],
    ...(code === "unsupported_document_visual" ? {
      details: [...new Set(visualDetails.map(({ docId, label }) =>
        documents.size > 1 ? `${docId}: ${label}` : label))],
    } : {}),
  }));
}
