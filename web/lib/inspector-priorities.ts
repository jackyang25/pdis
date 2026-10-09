import type { InspectionReviewView } from "./api.ts";
import { VERDICT_LABEL } from "./api.ts";
import type { PriorityFinding } from "./priorities.ts";

/**
 * How Inspector's result is read for its priority card: one finding per rubric unit.
 *
 * Every unit of the selected rubric, specified ones included, so the reading can say what is
 * in good shape as well as what is not. Document-consistency findings are left out: they are
 * checked once for the run, not by the rubric, and a card scoped to one rubric must not speak
 * for the others.
 */

export const INSPECTOR_PRIORITY_FOCUS =
  "Units this rubric requires that the document does not yet specify — missing, placeholder, "
  + "insufficient, vague or in conflict — and the sections where they cluster.";

export function inspectorPriorityFindings(review: InspectionReviewView): PriorityFinding[] {
  return (review.sections ?? []).flatMap((section) =>
    section.units.map((unit) => ({
      id: unit.id,
      // Named as the Sections tab names it: the variable, or the section when the unit is the
      // section itself. The section is the group only when it is not already the name.
      subject: unit.variable_name ?? section.section_name,
      group: unit.variable_name ? section.section_name : undefined,
      verdicts: [VERDICT_LABEL[unit.verdict] ?? unit.verdict],
      statements: [unit.statement],
      blockIds: unit.cited_block_ids,
    })),
  );
}
