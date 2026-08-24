/**
 * How a Scout result is organized for reading.
 *
 * The result is a **diamond, not a tree**: each field states one target, four independent
 * signals fan out from it, and then those signals *converge* on one shared pool of
 * insights, which converge again on findings. Rendering a diamond as a tree forces the
 * shared bottom to be copied under every branch — on a real 28-field run that was 937
 * redundant renders of the same insight, 51% of all insight rendering, because one insight
 * can be cited by grounding, precedent coverage, precedent outcome, precedent supporting,
 * and the relationship list at once.
 *
 * So the rule here: signals carry a **verdict and a citation**; insights live in one place.
 * Everything in this module is derivation over the saved result — no new data, no model
 * call, nothing the reader could not recompute. It is a module rather than page-local
 * helpers because these are the decisions worth a test, and a component cannot be asked
 * whether it dropped a citation.
 */

import type {
  Conformity,
  EvidenceAssessment,
  Match,
  PrecedentSignal,
  Variable,
} from "./api.ts";

/**
 * A number with its unit, spaced.
 *
 * `%` and `°` close up against the number; every other unit takes a space. Shared because
 * two call sites had already diverged - `formatNumericExpression` spaced it and the
 * benchmark formatter did not, which is where `1injections` and `0.6administration
 * occasions` came from.
 */
export function formatMeasure(value: number | null | undefined, unit: string): string {
  if (value == null || !Number.isFinite(value)) return "—";
  const formatted = value.toLocaleString(undefined, { maximumFractionDigits: 2 });
  if (!unit) return formatted;
  return /^[%°]/.test(unit) ? `${formatted}${unit}` : `${formatted} ${unit}`;
}

// --- The document's target ---------------------------------------------------

/**
 * One row of the target as the document stated it.
 *
 * `quote` always holds the span verbatim, whichever kind this is, so a row can never
 * carry less than the document said.
 */
export type TargetRow =
  | {
      kind: "bounded";
      /** The row's own name, e.g. "Product" or "Duration". */
      variable: string;
      minimum: string;
      optimistic: string;
      quote: string;
      blockIds: string[];
    }
  | { kind: "prose"; text: string; quote: string; blockIds: string[] };

const BOUNDED_MARKERS = { lead: "Variable:", minimum: ", Minimum:", optimistic: ", Optimistic:" };

/**
 * The target as rows, one per source span.
 *
 * `Variable.document_target` is a concatenation of `document_spans` - verified to
 * reconstruct it exactly on a real run - so the spans are strictly the better source:
 * already separated, and each carrying its own `block_ids`. Rendering the concatenation
 * was what produced a 995-character paragraph where the document had four table rows.
 *
 * Where a span is Chunker's serialization of a TPP table row
 * (`Variable: … , Minimum: … , Optimistic: …`) it is split into those three cells. That is
 * reading a delimited format this suite writes, not interpreting prose - and it is checked
 * rather than trusted: if the three parts do not account for the whole span, the row falls
 * back to prose. A row can lose formatting; it cannot lose text.
 */
export function documentTargetRows(
  spans: Variable["document_spans"] | undefined,
): TargetRow[] {
  return (spans ?? []).map((span) => {
    const quote = span.quote ?? "";
    const blockIds = span.block_ids ?? [];
    const bounded = splitBounded(quote);
    return bounded
      ? { kind: "bounded", ...bounded, quote, blockIds }
      : { kind: "prose", text: quote.trim(), quote, blockIds };
  });
}

function splitBounded(
  quote: string,
): { variable: string; minimum: string; optimistic: string } | null {
  const text = quote.trim();
  if (!text.startsWith(BOUNDED_MARKERS.lead)) return null;
  const minimumAt = text.indexOf(BOUNDED_MARKERS.minimum);
  if (minimumAt < 0) return null;
  const optimisticAt = text.indexOf(BOUNDED_MARKERS.optimistic, minimumAt);
  if (optimisticAt < 0) return null;
  const variable = text.slice(BOUNDED_MARKERS.lead.length, minimumAt).trim();
  const minimum = text
    .slice(minimumAt + BOUNDED_MARKERS.minimum.length, optimisticAt)
    .trim();
  const optimistic = text.slice(optimisticAt + BOUNDED_MARKERS.optimistic.length).trim();
  if (!variable || (!minimum && !optimistic)) return null;
  // The three cells must account for every word of the span. Checked by removing the
  // markers from the original and comparing what is left, rather than by reassembling:
  // reassembly compared marker *spacing* too, and the documents contain "injections. ,
  // Optimistic:" - a space before the comma - so a faithful split was rejected over
  // punctuation whitespace. This compares the text, which is what must not be lost.
  const withoutMarkers = normalize(
    text
      .replace(BOUNDED_MARKERS.lead, " ")
      .replace(BOUNDED_MARKERS.minimum, " ")
      .replace(BOUNDED_MARKERS.optimistic, " "),
  );
  const cells = normalize([variable, minimum, optimistic].join(" "));
  return withoutMarkers === cells ? { variable, minimum, optimistic } : null;
}

function normalize(value: string): string {
  return value.replace(/\s+/g, " ").trim();
}

// --- Relationships ----------------------------------------------------------

/**
 * Reading order for relation groups.
 *
 * Measured on a real run: `extends` 78%, `unrelated` 19%, `confirms` 2%,
 * `contradicts` 0.4% - 23 of 911 insights settle anything. So the ones that do are listed
 * first, and every group starts closed behind its count. Order and counts say where to
 * look; opening is the reader's, always.
 */
export const RELATION_READING_ORDER: Match["relation"][] = [
  "contradicts",
  "confirms",
  "extends",
  "unrelated",
];

export type RelationGroup = {
  relation: Match["relation"];
  matches: Match[];
};

export function relationGroups(matches: Match[]): RelationGroup[] {
  return RELATION_READING_ORDER.map((relation) => ({
    relation,
    matches: matches.filter((match) => match.relation === relation),
  })).filter((group) => group.matches.length > 0);
}

// --- The insight registry ---------------------------------------------------

/**
 * Every insight for one field, once, plus a lookup by id.
 *
 * This is the mechanism that removes the duplication. `supporting_insight_ids`,
 * `coverage_insight_ids` and `outcome_insight_ids` are *pointers* - the pipeline already
 * did the right thing - and a signal cites them rather than expanding each one into a
 * full copy of the insight and its sources.
 */
export type InsightRegistry = {
  byId: Map<string, Match>;
  /** Ordered groups, for the one place insights are drawn. */
  groups: RelationGroup[];
};

export function insightRegistry(matches: Match[]): InsightRegistry {
  const byId = new Map<string, Match>();
  for (const match of matches) {
    const id = match.insight.id;
    if (id && !byId.has(id)) byId.set(id, match);
  }
  return { byId, groups: relationGroups(matches) };
}

/**
 * What a signal's citation resolves to.
 *
 * `resolved` are insights the reader can jump to in the one list. `unresolvedCount` is
 * the ids that name no insight in this field's pool, and it is reported rather than
 * swallowed: a citation that silently resolves to nothing is how a reader comes to
 * believe a verdict rests on evidence that is not there.
 */
export type Citation = {
  resolved: Match[];
  unresolvedCount: number;
  total: number;
};

export function citation(ids: string[] | undefined, registry: InsightRegistry): Citation {
  const wanted = Array.from(new Set(ids ?? []));
  const resolved: Match[] = [];
  let unresolvedCount = 0;
  for (const id of wanted) {
    const match = registry.byId.get(id);
    if (match) resolved.push(match);
    else unresolvedCount += 1;
  }
  return { resolved, unresolvedCount, total: wanted.length };
}

/**
 * Whether a signal's own `supporting_findings` still has to be drawn.
 *
 * True when nothing its ids named could be found. Those Findings live nowhere else in the
 * result, so dropping this path would delete citations - the one place deduplicating by
 * reference could have lost data.
 */
export function needsFindingFallback(cited: Citation): boolean {
  return cited.resolved.length === 0;
}

// --- Calibration ------------------------------------------------------------

/**
 * How much of the calibration apparatus a target has earned.
 *
 * Measured on a real run: 10 of 12 targets had **zero** comparators, quartiles were
 * presentable for 0 of 12, an SD for 1 of 12, and the distribution plot had one point or
 * fewer in 11 of 12. The interface was built for the rare case and stated the common one
 * three times over - a bordered box, a bullet, and a disclaimer all saying "no
 * comparators".
 *
 * So the shape is chosen by what there is to show:
 *
 *   none     no comparable measurement. One line, said once.
 *   compact  one or two. The count, the values, the target's position - no grid.
 *   full     three or more. The grid earns its space, because an SD exists.
 *
 * The quartile and SD thresholds are the backend's presentation policy, mirrored rather
 * than reinvented: quartiles need four comparators, an SD needs three.
 */
export type CalibrationShape = "none" | "compact" | "full";

export type CalibrationView = {
  shape: CalibrationShape;
  showQuartiles: boolean;
  showDeviation: boolean;
  /** Where the target sits relative to what was observed. The decisive fact. */
  position: "above" | "below" | "within" | "unknown";
  meetingLabel: string;
};

export function calibrationView(conformity: Conformity): CalibrationView {
  const count = conformity.benchmark_count;
  const shape: CalibrationShape = count === 0 ? "none" : count < 3 ? "compact" : "full";
  return {
    shape,
    showQuartiles: count >= 4,
    showDeviation: count >= 3,
    position: targetPosition(conformity),
    meetingLabel:
      count > 0
        ? `${conformity.target_meeting_count} of ${count} meet target`
        : "",
  };
}

function targetPosition(conformity: Conformity): CalibrationView["position"] {
  const { benchmark_minimum: low, benchmark_maximum: high, target_value: value } = conformity;
  if (low == null || high == null || !Number.isFinite(value)) return "unknown";
  if (value > high) return "above";
  if (value < low) return "below";
  return "within";
}

// --- The run headline -------------------------------------------------------

/**
 * How much of the document was testable.
 *
 * Coverage, not verdicts: `selectScoutPriorities` already reports which targets external
 * evidence contradicts. What nothing else reports is how much of the document stated a
 * target at all, and how many of its numbers could be calibrated against anything - on a
 * real run 10 of 28 fields stated nothing and 15 of 18 numeric targets had no comparable
 * measurement. Every number here is counted from the result; nothing is inferred or graded.
 */
export type FieldSummaryInput = {
  variable: Variable;
  matches: Match[];
  assessment: EvidenceAssessment | null;
  precedent: PrecedentSignal | null;
  conformities: Conformity[];
};

export type RunHeadline = {
  /* No `conflictFields` or `confirmedFields`. Which fields are contradicted is
     `selectScoutPriorities`' first tier, and it reports them with the evidence, the reason
     and a source link. A second list of the same names is a second authority on the same
     fact, and the weaker one. */
  unfavorableFields: string[];
  wellGroundedCount: number;
  notStatedCount: number;
  unresolvedCount: number;
  fieldCount: number;
  /** Numeric targets that could not be calibrated for want of a comparable measurement. */
  uncalibratedTargets: number;
  numericTargets: number;
};

export function runHeadline(rows: FieldSummaryInput[]): RunHeadline {
  const named = (predicate: (row: FieldSummaryInput) => boolean) =>
    rows.filter(predicate).map((row) => row.variable.name);
  const conformities = rows.flatMap((row) => row.conformities);
  return {
    unfavorableFields: named((row) => row.precedent?.outcome === "unfavorable"),
    wellGroundedCount: rows.filter((row) => row.assessment?.strength === "well_grounded")
      .length,
    // Stated by the document or not: the distinction the reader needs before reading any
    // signal, because a field with no target was never analysed.
    notStatedCount: rows.filter(
      (row) => !(row.variable.document_target || "").trim(),
    ).length,
    unresolvedCount: rows.filter((row) => !row.variable.target_resolved).length,
    fieldCount: rows.length,
    uncalibratedTargets: conformities.filter((item) => item.benchmark_count === 0).length,
    numericTargets: conformities.length,
  };
}
