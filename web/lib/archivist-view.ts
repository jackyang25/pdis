/**
 * How an Archivist answer reads on screen.
 *
 * Here rather than inside the page for the reason the rest of `lib/` exists: these are
 * the decisions worth a test, and a component cannot be asked whether it merged two
 * document types.
 *
 * Every function below derives. Nothing is stored that a reader could recompute, which is
 * the same rule the corpus follows for counts - a stored total is a second authority that
 * can disagree with the list it came from.
 */

import { displayLabel } from "./display-label.ts";
import type {
  ArchivistAttributeGroup,
  ArchivistColumn,
  ArchivistDocument,
  ArchivistRecord,
  ArchivistSourceTypeGroup,
} from "./api.ts";

/** The local half of a qualified attribute name, as a reader should see it. */
export function attributeLabel(attribute: string): string {
  const local = attribute.includes(".")
    ? attribute.split(".").slice(1).join(".")
    : attribute;
  return displayLabel(local);
}

/**
 * How many documents answered, out of how many were asked.
 *
 * Both halves, always. "Three profiles set a shelf life" invites the reader to supply the
 * denominator themselves, and the denominator is the whole point: three of four is a
 * convention, three of nineteen is an outlier.
 */
export function answeredOf(group: ArchivistSourceTypeGroup): {
  answered: number;
  total: number;
} {
  const answered = new Set(group.values.map((record) => record.document_id));
  const total = new Set([
    ...answered,
    ...group.uncertain.map((record) => record.document_id),
    ...group.silent,
  ]);
  return { answered: answered.size, total: total.size };
}

export function attributeTotals(group: ArchivistAttributeGroup): {
  answered: number;
  total: number;
} {
  return group.groups.reduce(
    (running, source) => {
      const { answered, total } = answeredOf(source);
      return { answered: running.answered + answered, total: running.total + total };
    },
    { answered: 0, total: 0 },
  );
}

export type CollapsedValue = {
  stated: string;
  bound: string;
  records: ArchivistRecord[];
};

/**
 * The values of one document type, with identical answers collapsed into one row.
 *
 * Grouped on the document's own words, never on the parsed magnitude. Two profiles
 * saying "24 months" are one answer; a profile saying "2 years" is a different answer to
 * the same question, and folding them together would show a reader a number no document
 * wrote. The parse exists to sort within a unit, not to decide what counts as the same.
 */
export function collapseValues(records: ArchivistRecord[]): CollapsedValue[] {
  const buckets = new Map<string, CollapsedValue>();
  for (const record of records) {
    // The bound is part of the identity: a minimum of 24 months and an optimum of 24
    // months are two different claims that happen to share a number. So is the
    // condition - one shelf life for the lyophilized presentation is not the other.
    const key = [
      record.bound,
      record.stated.toLowerCase(),
      record.condition_stated.toLowerCase(),
    ].join(" | ");
    const bucket = buckets.get(key);
    if (bucket) bucket.records.push(record);
    else buckets.set(key, { stated: record.stated, bound: record.bound, records: [record] });
  }
  return [...buckets.values()].sort(byBoundThenMagnitude);
}

/** Minimum before optimal before single, then by parsed magnitude where there is one. */
function byBoundThenMagnitude(left: CollapsedValue, right: CollapsedValue): number {
  const order = ["minimum", "optimal", "single"];
  const byBound = order.indexOf(left.bound) - order.indexOf(right.bound);
  if (byBound !== 0) return byBound;
  const leftValue = left.records[0]?.magnitude;
  const rightValue = right.records[0]?.magnitude;
  if (leftValue != null && rightValue != null) return leftValue - rightValue;
  // A value that did not parse sorts after one that did, rather than being reordered
  // against a number it does not have.
  if (leftValue != null) return -1;
  if (rightValue != null) return 1;
  return 0;
}

export function documentTitle(
  documents: ArchivistDocument[],
  documentId: string,
): string {
  return documents.find((document) => document.id === documentId)?.title ?? documentId;
}

/** The columns a reader may filter on: the ones declaring a closed vocabulary. */
export function filterableColumns(columns: ArchivistColumn[]): ArchivistColumn[] {
  return columns.filter((column) => column.tags.length > 0);
}

/**
 * One sentence on what a column deliberately excludes.
 *
 * Shown because a reader judging a value needs to know what was kept out of it: a shelf
 * life column that never absorbed a storage temperature is a different column from one
 * that might have.
 */
export function fenceSummary(column: ArchivistColumn): string {
  if (column.not_confused_with.length === 0) return "";
  return `Kept separate from ${column.not_confused_with.map(attributeLabel).join(", ")}.`;
}
