import type { InspectionResult } from "./api.ts";
import { REASON_LABELS, worklist } from "./api.ts";
import type { PriorityItem } from "./priorities.ts";

/**
 * What Inspector puts at the top, and in what order.
 *
 * The one place that decides it. `PriorityPanel` renders whatever this returns and
 * knows nothing about rubrics, so changing what qualifies - or what it is allowed to
 * consider - is an edit to this file alone.
 *
 * Nothing is computed here. The order already exists on the result as `rank`,
 * assigned once during assembly from the finding's level and the sequence the rubric
 * author wrote. Re-deriving it in the view would be a second opinion that could
 * disagree with the one the sections show.
 */

/** Why this order, in the reader's words. Shown beneath the list. */
export const INSPECTOR_ORDER_NOTE =
  "Wording is Inspector's. The order is not: findings are sorted by level, then by "
  + "the order the rubric author wrote. Each one also appears in its own section below.";

export const INSPECTOR_EMPTY_MESSAGE =
  "Every unit the rubric requires is met, and no section conflicts with another.";

export function selectInspectorPriorities(
  inspection: InspectionResult,
): PriorityItem[] {
  return worklist(inspection).map((finding) => ({
    id: finding.id,
    label: finding.variable_name ?? finding.section_name ?? "Across sections",
    // The reason is the qualifier rather than part of the sentence, so a reader can
    // scan the column for one kind of problem.
    qualifier: REASON_LABELS[finding.reason] ?? finding.reason,
    statement: finding.statement,
    recommendation: finding.recommendation,
    blockIds: finding.cited_block_ids,
  }));
}
