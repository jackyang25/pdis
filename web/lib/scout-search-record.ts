/**
 * What was searched for one field, and what came back.
 *
 * `search_plan` is the complete record of every retrieval the run made: 754 of them on a
 * real run, across eleven lanes. Until now it was written to every result file and rendered
 * nowhere. The only account a reader had of retrieval was `Sources`, which is per insight
 * and therefore can only ever show a search that *found something*: 229 of 529 distinct
 * queries on that run, with 300 invisible.
 *
 * Those 300 are the ones that matter most for reading a verdict. "Unsupported" means two
 * opposite things depending on whether a field was searched sixty ways and came back empty
 * or was barely searched, and nothing in the interface could tell them apart.
 *
 * Grouped by lane rather than flat: a lane is what a reader recognises ("did it look in the
 * trial registries?"), and a flat list of sixty queries in retrieval order answers no
 * question anyone has.
 */

import type { ScoutResponse, SearchTrace } from "./api.ts";

export type SearchLaneGroup = {
  lane: string;
  /** One row per distinct query. The same query on one lane can be planned twice. */
  searches: SearchTrace[];
  /** Sources returned across the group, so a lane that ran and found nothing says so. */
  findingCount: number;
};

export type FieldSearchRecord = {
  /** Every search for the field, in reading order by lane. */
  groups: SearchLaneGroup[];
  total: number;
  /** Ran and returned. */
  completed: number;
  /** Ran and errored. Distinct from a lane that did not apply. */
  failed: number;
  /**
   * Not run, because the lane did not apply to this field.
   *
   * Kept apart from `failed` for the same reason the excluded panel separates a rejected
   * measurement from an unreadable one: one is a result, the other is an absence of one.
   */
  skipped: number;
};

/**
 * Lanes in the order a reader scans them: the broad ones first, then the registries, then
 * the structured biomedical sources. Anything unlisted keeps its position after these,
 * alphabetically, so adding a lane upstream needs no change here.
 */
const LANE_ORDER = [
  // Beside each other on purpose: these two are the same question asked two ways, and a
  // reader comparing them should not have to scroll between them.
  "web",
  "tavily",
  "pubmed",
  "semantic_scholar",
  "clinicaltrials",
  "isrctn",
  "ctis",
  "fda",
  "fda_safety",
  "open_targets",
  "chembl",
  "uniprot",
];

export function fieldSearchRecord(
  result: Pick<ScoutResponse, "search_plan">,
  attributeRef: string,
): FieldSearchRecord {
  const mine = (result.search_plan ?? []).filter(
    (trace) => trace.attribute_ref === attributeRef,
  );

  const byLane = new Map<string, SearchTrace[]>();
  for (const trace of mine) {
    // One row per distinct query on a lane. The planner can emit the same query twice when
    // two intents converge on it, and a reader counting rows should be counting searches.
    const existing = byLane.get(trace.lane) ?? [];
    if (!existing.some((seen) => seen.query === trace.query)) existing.push(trace);
    byLane.set(trace.lane, existing);
  }

  const groups: SearchLaneGroup[] = [...byLane.entries()]
    .map(([lane, searches]) => ({
      lane,
      searches,
      findingCount: searches.reduce((sum, trace) => sum + (trace.finding_count ?? 0), 0),
    }))
    .sort((left, right) => {
      const leftAt = LANE_ORDER.indexOf(left.lane);
      const rightAt = LANE_ORDER.indexOf(right.lane);
      if (leftAt !== rightAt) {
        if (leftAt < 0) return 1;
        if (rightAt < 0) return -1;
        return leftAt - rightAt;
      }
      return left.lane.localeCompare(right.lane);
    });

  const counted = groups.flatMap((group) => group.searches);
  return {
    groups,
    total: counted.length,
    completed: counted.filter((trace) => trace.status === "complete").length,
    failed: counted.filter((trace) => trace.status === "failed").length,
    skipped: counted.filter((trace) => trace.status === "skipped").length,
  };
}

/**
 * The headline, as one sentence.
 *
 * Built here rather than in the view, like `calibrationView`'s: two constructions of one
 * sentence is how "62 searches" and "62 run" come to disagree about the wording.
 */
export function searchRecordSummary(record: FieldSearchRecord): string {
  if (record.total === 0) return "No search was planned for this field.";
  const parts = [`${record.total} search${record.total === 1 ? "" : "es"} planned`];
  if (record.skipped > 0) parts.push(`${record.skipped} not applicable`);
  if (record.failed > 0) parts.push(`${record.failed} failed`);
  return `${parts.join(" · ")}.`;
}
