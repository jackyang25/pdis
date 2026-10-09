import type { Match, ScoutResponse } from "./api.ts";
import { sortMatchesForReading } from "./scout-match-order.ts";
import {
  CALIBRATION_BASIS_LABEL,
  GROUNDING_LABEL,
  OUTCOME_LABEL,
  PRECEDENT_LABEL,
  RELATIONSHIP_LABEL,
  displayAttributeLabel,
} from "./scout-labels.ts";
import type { PriorityFinding } from "./priorities.ts";

/**
 * How Scout's result is read for its priority card: one finding per field.
 *
 * A field is what Scout's own Fields tab is organised by, and what a reader acts on. Its
 * axes stay separate verdict lines - grounding, how insights relate to the target, precedent,
 * and each calibrated target - because they are orthogonal and nothing here may blend them
 * into one label. Names and labels come from the same helpers the Fields tab uses.
 */

export const SCOUT_PRIORITY_FOCUS =
  "Targets the evidence contradicts, targets with little or no supporting evidence, and "
  + "quantitative targets the comparator cohort does not meet.";

/** Contradicting insights quoted per field. The rest are counted; the field lists them all. */
const CONTRADICTIONS_QUOTED = 3;

/** Scope for insights that name no document field. */
const PROGRAM_ID = "program";

export function scoutPriorityFindings(result: ScoutResponse): PriorityFinding[] {
  const fields = result.variables ?? [];
  const known = new Set(fields.map((field) => field.name));
  const matchesByField = new Map<string, Match[]>();
  for (const match of sortMatchesForReading(result.matches ?? [])) {
    if (match.relation === "unrelated") continue;
    const ref = match.insight.attribute_ref;
    const key = ref && known.has(ref) ? ref : PROGRAM_ID;
    matchesByField.set(key, [...(matchesByField.get(key) ?? []), match]);
  }

  const findings: PriorityFinding[] = fields.map((field) => {
    const assessment = (result.assessments ?? []).find((item) => item.attribute_ref === field.name);
    const precedent = (result.precedents ?? []).find((item) => item.attribute_ref === field.name);
    const scores = (result.conformity ?? []).filter((score) => score.attribute_refs.includes(field.name));
    const matches = matchesByField.get(field.name) ?? [];
    const contradicting = matches.filter((match) => match.relation === "contradicts");
    const verdicts = [
      // Whether there was anything to test comes first, in the run headline's words: a
      // field with no target, or one whose target could not be interpreted, was never
      // analysed, which is a different fact from evidence being thin.
      ...(!field.document_target.trim()
        ? ["No target stated"]
        : !field.target_resolved
          ? ["Interpretation unresolved"]
          : []),
      ...(assessment ? [GROUNDING_LABEL[assessment.strength]] : []),
      ...relationCounts(matches),
      ...(precedent
        ? [`${PRECEDENT_LABEL[precedent.precedent]} · ${OUTCOME_LABEL[precedent.outcome]}`]
        : []),
      // Code's own count, so a verdict line and never a statement.
      ...scores.map((score) =>
        score.calibration_status === "insufficient"
          ? `${score.target_quote || score.target_label}: ${CALIBRATION_BASIS_LABEL.insufficient} comparators to calibrate`
          : `${score.target_quote || score.target_label}: ${score.verdict} (${score.benchmark_count} measured)`,
      ),
    ];
    return {
      id: field.name,
      subject: displayAttributeLabel(field.name),
      // Never empty: a field nothing was found for says so, rather than arriving blank.
      verdicts: verdicts.length > 0 ? verdicts : ["No evidence assessed"],
      statements: [
        assessment?.reason ?? "",
        ...contradicting
          .slice(0, CONTRADICTIONS_QUOTED)
          .flatMap((match) => [match.insight.statement, match.reason]),
        precedent?.reason ?? "",
      ].filter(Boolean),
      quote: field.target_resolved ? field.document_target : undefined,
      blockIds: [
        ...new Set([
          ...(field.block_ids ?? []),
          ...(assessment?.doc_block_ids ?? []),
          ...contradicting.flatMap((match) => match.doc_block_ids ?? []),
        ]),
      ],
    };
  });

  // Insights bound to no document field still say something about the program, and are
  // shown under "Program-wide" on the page; leaving them out would hide a contradiction.
  const program = matchesByField.get(PROGRAM_ID) ?? [];
  if (program.length > 0) {
    const contradicting = program.filter((match) => match.relation === "contradicts");
    findings.push({
      id: PROGRAM_ID,
      subject: displayAttributeLabel(PROGRAM_ID),
      verdicts: relationCounts(program),
      statements: contradicting
        .slice(0, CONTRADICTIONS_QUOTED)
        .flatMap((match) => [match.insight.statement, match.reason])
        .filter(Boolean),
      blockIds: [...new Set(contradicting.flatMap((match) => match.doc_block_ids ?? []))],
    });
  }
  return findings;
}

/** "Conflicts: 2 insights", one line per relation that occurs, in the page's own words. */
function relationCounts(matches: Match[]): string[] {
  const counts = new Map<Match["relation"], number>();
  for (const match of matches) counts.set(match.relation, (counts.get(match.relation) ?? 0) + 1);
  return [...counts].map(
    ([relation, count]) => `${RELATIONSHIP_LABEL[relation]}: ${count} insight${count === 1 ? "" : "s"}`,
  );
}
