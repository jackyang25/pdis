/**
 * How a Drafter run is laid out for a reader: which panel each variable sits in, and the
 * short forms its suggestion and figures are written in. Pure, so the page decides
 * nothing the tests cannot see.
 */

import type {
  DraftBasis,
  DraftGroupSummary,
  DraftObservation,
  DraftResult,
  DraftSuggestion,
  DraftVariable,
} from "./api.ts";
import { formatMeasure, formatMeasurePair } from "./measure-format.ts";
import { formatPublishedMonth } from "./published-date.ts";
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
      // Not the description: it is the definition the model reads, not shown on the row, and
      // a match on text the reader cannot see reads as a broken search.
      && matchesQuery(
        query,
        variable.label,
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

/** One passage of a source, quoted once, with every product it was read as speaking for. */
export type EvidencePassage = {
  quote: string;
  products: string[];
  figure: string;
};

/** One source and what it said about the variable: one entry however many products it names. */
export type EvidenceSource = {
  url: string;
  title: string;
  source_label: string;
  /** When the source says it was published, at the precision it stated; null when it did not. */
  published: string | null;
  cited: boolean;
  passages: EvidencePassage[];
};

/**
 * A basis's evidence by source, cited first.
 *
 * Grouped by URL because one page often names several products: listed per observation,
 * the same title repeated once per product and the list read as more sources than it held.
 * Cited sources lead so a reader checks what the suggestion rests on before the rest; the
 * order within each half is the run's.
 */
export function evidenceSources(variable: DraftVariable, basis: DraftBasis): EvidenceSource[] {
  const cited = new Set(variable.suggestion?.basis_ids ?? []);
  const byUrl = new Map<string, EvidenceSource>();
  for (const observation of variable.observations) {
    if (observation.basis !== basis) continue;
    const source = byUrl.get(observation.url) ?? {
      url: observation.url,
      title: observation.title,
      source_label: observation.source_label,
      published: formatPublishedMonth(observation.published_at, observation.published_precision),
      cited: false,
      passages: [],
    };
    source.cited ||= cited.has(observation.id);
    byUrl.set(observation.url, source);
    // A review article naming three products is one sentence read three times. Quoted
    // three times it filled the panel with the same words; a different figure is a
    // different reading and keeps its own line.
    const figure = observationFigure(observation.value);
    const passage = source.passages.find((item) => item.quote === observation.quote && item.figure === figure);
    if (!passage) source.passages.push({ quote: observation.quote, products: [observation.product].filter(Boolean), figure });
    else if (observation.product && !passage.products.includes(observation.product)) passage.products.push(observation.product);
  }
  const sources = [...byUrl.values()];
  return [...sources.filter((source) => source.cited), ...sources.filter((source) => !source.cited)];
}

/** What one observation states, as written: a value or a range, in its own unit. */
export function observationFigure(value: DraftObservation["value"]): string {
  if (!value) return "";
  if (value.value != null) return formatMeasure(value.value, value.unit);
  if (value.lower != null && value.upper != null) return formatMeasurePair(value.lower, value.upper, value.unit, "–");
  return "";
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
