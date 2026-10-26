import type { ContentBlock } from "./api";

export type DocumentBlockPresentation =
  | "heading-primary"
  | "heading-secondary"
  | "heading-tertiary"
  | "table-row"
  | "body";

export type DocumentTraceRailMode = "inline" | "external";

/** Where the trace shows a result's details: beside the document, or over it. */
export type DocumentTracePanelMode = "aside" | "sheet";

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
  /**
   * Where the header's own words end. The parser joins header and value with ": ", so
   * the header ends there, not at the value: a header drawn to the value showed the
   * separator as if the document had written it.
   */
  headerEnd: number;
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
    const headerEnd = contentStart + header.length;
    cells.push({
      columnIndex,
      header,
      value,
      contentStart,
      contentEnd,
      headerEnd: block.content.slice(contentStart, headerEnd) === header && headerEnd <= valueStart
        ? headerEnd
        : valueStart,
      valueStart,
      valueEnd,
    });
  }

  return { columnCount: headers.length, cells };
}

/**
 * Whether a table row carries on the table of the row before it, by the same column headers.
 *
 * The parser repeats the headers in every row, so each row's cells can be cited alone. A
 * reader needs them once: the trace states them in full on a table's first row and in one
 * line on the rows after, where they still name a column for a reader who arrives mid-table.
 */
export function documentTableRowContinues(
  previous: ContentBlock | undefined,
  block: ContentBlock,
): boolean {
  if (!previous || previous.block_type !== "table_row" || block.block_type !== "table_row") return false;
  const headers = (row: ContentBlock) => JSON.stringify(row.structural_meta.column_headers ?? null);
  return headers(previous) === headers(block);
}

export function documentTraceRailMode(
  containerWidth: number,
): DocumentTraceRailMode {
  return Number.isFinite(containerWidth) && containerWidth >= 640
    ? "external"
    : "inline";
}

/** Width of the details panel when it sits beside the document, in px (22rem). */
const PANEL_ASIDE_WIDTH = 352;
/** Least a document column may be reduced to and still read as prose, in px (28rem). */
const DOCUMENT_MIN_WIDTH = 448;

/**
 * Whether the details panel fits beside the document or has to cover it.
 *
 * Measured against what the two columns actually need, not against a viewport
 * breakpoint. It was `containerWidth < 1024`, and the app shell caps its content at
 * 1120px: after the shell's padding no page can hand the trace more than about 1056px,
 * so the threshold sat ~30px below the widest container that will ever exist. Any page
 * differing by a scrollbar or a little padding fell on the other side of it, which is
 * how one tool showed a bottom sheet at full screen while its neighbours showed the
 * panel — with nothing about the window explaining the difference.
 */
export function documentTracePanelMode(
  containerWidth: number,
): DocumentTracePanelMode {
  return Number.isFinite(containerWidth)
    && containerWidth >= PANEL_ASIDE_WIDTH + DOCUMENT_MIN_WIDTH
    ? "aside"
    : "sheet";
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
