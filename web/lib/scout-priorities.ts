import type { EvidenceAssessment, Match, ScoutResponse } from "./api.ts";
import { sortMatchesForReading } from "./scout-match-order.ts";
import { PRIORITY_LIMIT, type PriorityItem } from "./priorities.ts";

/**
 * What Scout puts at the top, and in what order.
 *
 * PLACEHOLDER RANKING. Scout has no authored rubric to rank against - Inspector's
 * order comes from the sequence a rubric author wrote, and Scout has no equivalent.
 * Until domain experts supply one, this orders by signals the result already
 * publishes rather than by a score invented here:
 *
 *   1. a target the evidence CONTRADICTS - the strongest claim Scout can make
 *   2. a target nothing supports - `strength` of `unsupported`, then `thin`
 *   3. a quantitative target the comparator cohort does not meet
 *
 * Each tier is an existing published field, so nothing is weighted, blended, or
 * scored. What is missing is any sense of which *variable* matters more, and that is
 * exactly the judgment a rubric would supply.
 *
 * To improve it, edit this file and nothing else:
 *   - change what qualifies, or the tier order, below
 *   - narrow or widen what it may consider by changing what the caller passes
 * `PriorityPanel` renders whatever comes back and has no opinion about any of it.
 */

export const SCOUT_ORDER_NOTE =
  "Wording is Scout's. The order is a placeholder until a rubric defines what "
  + "matters most: contradicted targets first, then targets no evidence supports, "
  + "then targets the comparator cohort does not meet. Every item also appears in "
  + "the fields below.";

export const SCOUT_EMPTY_MESSAGE =
  "No contradicted targets, unsupported targets, or unmet quantitative targets were found.";

/**
 * How many to show.
 *
 * The shared cap, not a second copy of the number. Scout stops selecting at the limit
 * rather than selecting everything and truncating, because its tiers are appended in
 * priority order - the two give the same eight, and stopping early skips work.
 */
export const SCOUT_PRIORITY_LIMIT = PRIORITY_LIMIT;

/** Weakest evidence first; anything stronger is not raised here. */
const RAISED_STRENGTHS: EvidenceAssessment["strength"][] = ["unsupported", "thin"];

function label(attributeRef: string): string {
  return attributeRef
    .split(".")
    .slice(-1)[0]
    .replace(/_/g, " ")
    .replace(/^./, (c) => c.toUpperCase());
}

function contradictedTargets(result: ScoutResponse): PriorityItem[] {
  const matches = (result.matches ?? []).filter(
    (match: Match) => match.relation === "contradicts",
  );
  // Reuse the reading order the fields already use, so the panel cannot present a
  // different sequence from the list a reader scrolls to next.
  return sortMatchesForReading(matches).map((match) => ({
    id: `contradicts:${match.insight.id ?? match.insight.statement}`,
    label: label(match.insight.attribute_ref ?? "target"),
    qualifier: "Evidence contradicts this target",
    statement: match.insight.statement,
    recommendation: match.reason,
    blockIds: match.doc_block_ids,
  }));
}

function unsupportedTargets(result: ScoutResponse): PriorityItem[] {
  const byStrength = (assessment: EvidenceAssessment) =>
    RAISED_STRENGTHS.indexOf(assessment.strength);
  return (result.assessments ?? [])
    .filter((assessment) => RAISED_STRENGTHS.includes(assessment.strength))
    .slice()
    .sort((a, b) => byStrength(a) - byStrength(b))
    .map((assessment) => ({
      id: `strength:${assessment.attribute_ref}`,
      label: label(assessment.attribute_ref),
      qualifier:
        assessment.strength === "unsupported"
          ? "No evidence supports this target"
          : "Thin evidence for this target",
      statement: assessment.doc_target || assessment.reason,
      recommendation: assessment.doc_target ? assessment.reason : "",
      blockIds: assessment.doc_block_ids,
    }));
}

function unmetQuantitativeTargets(result: ScoutResponse): PriorityItem[] {
  return (result.conformity ?? [])
    .filter(
      (score) =>
        // Only where a cohort actually exists to compare against; "insufficient"
        // means Scout could not calibrate, which is not the same as falling short.
        score.calibration_status !== "insufficient"
        && score.benchmark_count > 0
        && score.target_meeting_rate === 0,
    )
    .map((score) => ({
      id: `conformity:${score.target_id}`,
      label: label(score.attribute_refs[0] ?? "target"),
      qualifier: `No comparator met this target (${score.benchmark_count} measured)`,
      statement: score.target_label,
      recommendation: score.verdict,
      blockIds: score.doc_block_ids,
    }));
}

export function selectScoutPriorities(result: ScoutResponse): PriorityItem[] {
  const tiers = [
    contradictedTargets(result),
    unsupportedTargets(result),
    unmetQuantitativeTargets(result),
  ];
  const seen = new Set<string>();
  const items: PriorityItem[] = [];
  for (const tier of tiers) {
    for (const item of tier) {
      // A target can be both contradicted and unsupported; the stronger claim wins
      // and it is raised once.
      if (seen.has(item.label)) continue;
      seen.add(item.label);
      items.push(item);
      if (items.length >= SCOUT_PRIORITY_LIMIT) return items;
    }
  }
  return items;
}
