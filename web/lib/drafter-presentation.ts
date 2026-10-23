/**
 * How a Drafter run is laid out for a reader: which panel each variable sits in, and the
 * short forms its suggestion and figures are written in. Pure, so the page decides
 * nothing the tests cannot see.
 */

import type { DraftGroupSummary, DraftResult, DraftSuggestion, DraftVariable } from "./api.ts";
import { matchesQuery } from "./result-search.ts";

export type DrafterPanelId = "suggested" | "insufficient" | "failed";

/**
 * In the order a reviewer works: the suggestions that need a decision, then the variables
 * left for them to write, then those the run could not finish.
 */
export const DRAFTER_PANELS: readonly { id: DrafterPanelId; title: string; description: string }[] = [
  {
    id: "suggested",
    title: "Suggested targets",
    description: "Each rests on the evidence listed with it. Check it there before using it."
  },
  {
    id: "insufficient",
    title: "Not enough evidence",
    description: "The sources found could not support a suggestion.",
  },
  {
    id: "failed",
    title: "Could not be suggested",
    description: "The run could not finish these variables. Running again may fill them in.",
  },
];

export function panelOf(variable: DraftVariable): DrafterPanelId {
  if (variable.status === "failed") return "failed";
  return variable.suggestion?.kind === "insufficient" ? "insufficient" : "suggested";
}

export function panelVariables(result: DraftResult, panel: DrafterPanelId, query: string): DraftVariable[] {
  return result.variables.filter(
    (variable) =>
      panelOf(variable) === panel
      && matchesQuery(
        query,
        variable.label,
        variable.description,
        variable.suggestion?.statement,
        variable.suggestion?.minimum,
        variable.suggestion?.preferred,
      ),
  );
}

export function countVariables(result: DraftResult): Record<DrafterPanelId | "total", number> {
  const counts = { total: result.variables.length, suggested: 0, insufficient: 0, failed: 0 };
  for (const variable of result.variables) counts[panelOf(variable)] += 1;
  return counts;
}

export function suggestionLines(suggestion: Pick<DraftSuggestion, "minimum" | "preferred" | "statement">): string[] {
  if (suggestion.statement.trim()) return [suggestion.statement.trim()];
  return [
    suggestion.minimum.trim() ? `Minimum ${suggestion.minimum.trim()}` : "",
    suggestion.preferred.trim() ? `Preferred ${suggestion.preferred.trim()}` : "",
  ].filter(Boolean);
}

function figure(value: number): string {
  return Number.isInteger(value) ? String(value) : String(Number(value.toFixed(3)));
}

/**
 * One group of values stated in one unit. Units are never pooled, and the line says
 * "values stated in", not "comparable values": a group may span different endpoints and
 * repeat one product, so it is not one measured cohort.
 */
export function figureLine(group: DraftGroupSummary): string {
  return (
    `${group.count} values stated in ${group.unit}: median ${figure(group.median)}, `
    + `middle half ${figure(group.lower_quartile)}–${figure(group.upper_quartile)}, `
    + `range ${figure(group.minimum)}–${figure(group.maximum)}`
  );
}

/**
 * The outcome row. Suggested and not enough evidence are a model's readings, so they show
 * at zero. Could not be suggested is a failure count, shown only when there is one.
 */
export function drafterMetricItems(result: DraftResult): { label: string; count: number; tone: "info" | "warning" | "neutral" }[] {
  const counts = countVariables(result);
  return [
    { label: "Suggested", count: counts.suggested, tone: "info" },
    { label: "Not enough evidence", count: counts.insufficient, tone: "warning" },
    ...(counts.failed > 0 ? [{ label: "Could not be suggested", count: counts.failed, tone: "neutral" as const }] : []),
  ];
}
