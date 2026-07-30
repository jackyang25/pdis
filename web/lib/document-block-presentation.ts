import type { ContentBlock } from "./api";

export type DocumentBlockPresentation =
  | "heading-primary"
  | "heading-secondary"
  | "heading-tertiary"
  | "table-row"
  | "body";

export type DocumentTraceRailMode = "inline" | "external";

export type DocumentBlockSpacing =
  | "major"
  | "section"
  | "subsection"
  | "body"
  | "continuation";

export type DocumentTableCell = {
  columnIndex: number;
  header: string;
  value: string;
  contentStart: number;
  contentEnd: number;
  valueStart: number;
  valueEnd: number;
};

export type DocumentTableRow = {
  columnCount: number;
  cells: DocumentTableCell[];
};

function finiteInteger(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value) && value >= 0;
}

export function documentTableCells(block: ContentBlock): DocumentTableRow | null {
  if (block.block_type !== "table_row") return null;
  const headers = block.structural_meta.column_headers;
  const rawCells = block.structural_meta.table_cells;
  if (!Array.isArray(headers) || !headers.every((header) => typeof header === "string")) {
    return null;
  }
  if (!headers.length || !Array.isArray(rawCells) || !rawCells.length) return null;

  const cells: DocumentTableCell[] = [];
  const seenColumns = new Set<number>();
  for (const rawCell of rawCells) {
    if (!rawCell || typeof rawCell !== "object" || Array.isArray(rawCell)) return null;
    const record = rawCell as Record<string, unknown>;
    const columnIndex = record.column_index;
    const header = record.header;
    const value = record.value;
    const contentStart = record.content_start;
    const contentEnd = record.content_end;
    const valueStart = record.value_start;
    const valueEnd = record.value_end;
    if (
      !finiteInteger(columnIndex)
      || columnIndex >= headers.length
      || seenColumns.has(columnIndex)
      || typeof header !== "string"
      || header !== headers[columnIndex].trim()
      || typeof value !== "string"
      || !finiteInteger(contentStart)
      || !finiteInteger(contentEnd)
      || !finiteInteger(valueStart)
      || !finiteInteger(valueEnd)
      || contentStart > valueStart
      || valueStart > valueEnd
      || valueEnd > contentEnd
      || contentEnd > block.content.length
      || block.content.slice(valueStart, valueEnd) !== value
    ) {
      return null;
    }
    seenColumns.add(columnIndex);
    cells.push({
      columnIndex,
      header,
      value,
      contentStart,
      contentEnd,
      valueStart,
      valueEnd,
    });
  }

  return { columnCount: headers.length, cells };
}

export function documentTraceRailMode(
  containerWidth: number,
): DocumentTraceRailMode {
  return Number.isFinite(containerWidth) && containerWidth >= 640
    ? "external"
    : "inline";
}

export function documentBlockSpacing(
  presentation: DocumentBlockPresentation,
): DocumentBlockSpacing {
  switch (presentation) {
    case "heading-primary":
      return "major";
    case "heading-secondary":
      return "section";
    case "heading-tertiary":
      return "subsection";
    case "table-row":
      return "continuation";
    case "body":
      return "body";
  }
}

export function documentBlockPresentation(
  block: ContentBlock,
): DocumentBlockPresentation {
  if (block.block_type === "table_row") {
    return "table-row";
  }
  if (block.block_type !== "heading") {
    return "body";
  }

  const level = block.structural_meta.heading_level;
  if (typeof level !== "number" || !Number.isFinite(level)) {
    return "heading-secondary";
  }
  if (level <= 1) {
    return "heading-primary";
  }
  if (level === 2) {
    return "heading-secondary";
  }
  return "heading-tertiary";
}
