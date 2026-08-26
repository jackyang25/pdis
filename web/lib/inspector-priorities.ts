import type { InspectionResult } from "./api.ts";
import { VERDICT_LABEL, worklist } from "./api.ts";
import type { PriorityItem } from "./priorities.ts";

/**
 * What Inspector puts at the top, and in what order.
 *
 * The one place that decides it. `PriorityPanel` renders whatever this returns and
 * knows nothing about rubrics, so changing what qualifies - or what it is allowed to
 * consider - is an edit to this file alone.
 *
 * Nothing is computed here. The order already exists on the result as `rank`,
 * assigned once during assembly from the verdict's place in the published vocabulary
 * and the sequence the rubric author wrote. Re-deriving it in the view would be a
 * second opinion that could disagree with the one the sections show.
 */

/** Why this order, in the reader's words. Shown beneath the list. */
export const INSPECTOR_ORDER_NOTE =
  "Wording is Inspector's. The order is not: units are sorted by verdict, worst "
  + "first, then by the order the rubric author wrote. Each one also appears in its "
  + "own section below.";

export const INSPECTOR_EMPTY_MESSAGE =
  "Every unit the rubric requires is specified, and no section conflicts with another.";

export function selectInspectorPriorities(
  inspection: InspectionResult,
): PriorityItem[] {
  return worklist(inspection).map((item) => ({
    id: item.id,
    label: item.variable_name ?? item.section_name ?? "Across sections",
    // The verdict is the qualifier rather than part of the sentence, so a reader can
    // scan the column for one kind of problem.
    qualifier: VERDICT_LABEL[item.verdict] ?? item.verdict,
    statement: item.statement,
    blockIds: item.cited_block_ids,
  }));
}
