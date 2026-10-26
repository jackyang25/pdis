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
  ContentBlock,
  Conformity,
  EvidenceAssessment,
  Finding,
  IdentityReconciliation,
  Match,
  PrecedentSignal,
  RetrievalScope,
  RunScopeDimension,
  ScoutResponse,
  Variable,
  EvidenceStrength,
  NumericDisplay,
  NumericExpression,
  QuantitativeTarget,
} from "./api.ts";
import { RUN_SCOPE_DIMENSIONS } from "./api.ts";
import { documentTableCells, tableHeaderLabel } from "./document-block-presentation.ts";
import { countLabel } from "./count-label.ts";
import { displayLabel } from "./display-label.ts";
import { displayAttributeLabel } from "./scout-labels.ts";
import { formatMeasure, formatMeasurePair } from "./measure-format.ts";

/** A numeric expression in one short line: "≥ 80%", or "2–8 °C" for a range. */
export function formatNumericExpression(expression: NumericExpression): string {
  const unit = expression.unit ?? "";
  if (
    expression.kind === "range" ||
    expression.kind === "confidence_interval"
  ) {
    return expression.lower == null || expression.upper == null
      ? "Unresolved numeric expression"
      : formatMeasurePair(expression.lower, expression.upper, unit, "–", expression.display);
  }
  if (expression.value == null) return "Unresolved numeric expression";
  return `${expression.comparator} ${formatMeasure(expression.value, unit, expression.display)}`.trim();
}

/**
 * A calibrated target in one short line: its expression when the ledger still holds it,
 * otherwise the score's own comparator and value. Never `target_label`, which flattens every
 * semantic slot into one line two hundred characters long.
 */
export function conformityTargetLabel(
  conformity: Conformity,
  target: QuantitativeTarget | null,
): string {
  return target
    ? formatNumericExpression(target.expression)
    : `${conformity.comparator} ${formatMeasure(conformity.target_value, conformity.unit)}`;
}

/**
 * Why a measurement was left out, split by who established it.
 *
 * `checks` are deterministic: a fact about the source's own numbers, which cannot be wrong.
 * `judgment` is a model's reading of whether the source measures the same thing, which can
 * be. They were one dot-joined paragraph, so the interface rendered the facts in the tone
 * that means "a model wrote this".
 *
 * `other` is whatever neither field claims: a reviewer's own words, or the tool's
 * needs-review sentence.
 *
 * Most of this function is the older saved results. Before `structural_reasons` existed the
 * two kinds were joined, and the model's reason was stored with a `semantic status: X - `
 * prefix and could appear twice. Matching on equality alone left the prefixed copy behind, so
 * the reason showed once cleanly and once again inside the leftovers. `endsWith` catches both
 * forms, and the set collapses the repeats. Exact string work, not pattern matching: the
 * prefix is prepended to the reason verbatim.
 */
export function exclusionReasonLines(measurement: {
  exclusion_reasons?: string[];
  structural_reasons?: string[];
  semantic_status?: string;
  semantic_reason?: string;
}): { checks: string[]; judgment: string; other: string[] } {
  const checks = measurement.structural_reasons ?? [];
  const judgment =
    measurement.semantic_status !== "comparable" ? measurement.semantic_reason || "" : "";
  const other = Array.from(
    new Set(
      (measurement.exclusion_reasons ?? []).filter(
        (reason) =>
          !checks.includes(reason) && !(judgment !== "" && reason.endsWith(judgment)),
      ),
    ),
  );
  return { checks, judgment, other };
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
      kind: "table";
      /** The table row's cells: each column's title line, its whole heading, and the value. */
      cells: { label: string; header: string; value: string }[];
      quote: string;
      blockIds: string[];
    }
  | { kind: "prose"; text: string; quote: string; blockIds: string[] };

/**
 * The target as rows, one per source span.
 *
 * `Variable.document_target` is a concatenation of `document_spans` - verified to
 * reconstruct it exactly on a real run - so the spans are strictly the better source:
 * already separated, and each carrying its own `block_ids`. Rendering the concatenation
 * was what produced a 995-character paragraph where the document had four table rows.
 *
 * A span that is a whole table row is shown as that row's cells, read from the cells the
 * parser recorded for its block, never from the span's wording. This read the wording
 * before, by the markers ", Minimum:" and ", Optimistic:", and a template whose columns were
 * headed "Minimum The minimal target should be…" fell through to the raw paragraph. Any other
 * span - part of a row, or prose - stays as the document's words.
 */
export function documentTargetRows(
  spans: Variable["document_spans"] | undefined,
  blocksById: ReadonlyMap<string, ContentBlock> = new Map(),
): TargetRow[] {
  return (spans ?? []).map((span) => {
    const quote = span.quote ?? "";
    const blockIds = span.block_ids ?? [];
    const block = blockIds.length === 1 ? blocksById.get(blockIds[0]) : undefined;
    // Whitespace aside: a quote reads a cell's line break as a space.
    const row = block && collapse(block.content) === collapse(quote) ? documentTableCells(block) : null;
    return row
      ? { kind: "table", cells: row.cells.map((cell) => ({ label: tableHeaderLabel(cell.header), header: collapse(cell.header), value: cell.value.trim() })), quote, blockIds }
      : { kind: "prose", text: quote.trim(), quote, blockIds };
  });
}

function collapse(text: string): string {
  return text.replace(/\s+/g, " ").trim();
}

/** The target in one line: a table row's values, prose as written. */
export function documentTargetText(rows: TargetRow[]): string {
  return rows
    .map((row) => (row.kind === "table" ? row.cells.map((cell) => cell.value).filter(Boolean).join(" · ") : row.text))
    .join(" ");
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
  // Last and kept: no relation was obtained, which says nothing about the target, but a
  // group order without it would drop the insight from its field without a trace.
  "not_assessed",
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

// --- Sources -----------------------------------------------------------------

/**
 * Who a cited source is: its record identity, or its URL where a saved finding states none.
 *
 * Not the URL alone. One trial reached through its registry page and a mirror is one record,
 * and counting links would count it twice - the service contract keys lineage the same way.
 */
export function sourceIdentity(finding: Pick<Finding, "url" | "record_key">): string {
  return finding.record_key ? `record:${finding.record_key}` : `url:${finding.url}`;
}

/** Distinct sources cited anywhere in the result, one per record. */
export function distinctSourceCount(
  result: Pick<
    ScoutResponse,
    "matches" | "assessments" | "precedents" | "conformity" | "development_landscape" | "safety_observations"
  >,
): number {
  const findings: Finding[] = [
    ...(result.matches ?? []).flatMap((match) => match.insight.supporting_findings ?? []),
    ...(result.assessments ?? []).flatMap((item) => item.supporting_findings ?? []),
    ...(result.precedents ?? []).flatMap((item) => item.supporting_findings ?? []),
    ...(result.development_landscape ?? []).flatMap((item) => item.supporting_findings ?? []),
    ...(result.safety_observations ?? []).flatMap((item) => item.supporting_findings ?? []),
  ].filter((finding) => finding.url || finding.record_key);
  const byUrl = new Map(findings.map((finding) => [finding.url, sourceIdentity(finding)]));
  const sources = new Set(findings.map(sourceIdentity));
  // A measurement names only the page it was read from, so it is counted as the record
  // that page belongs to.
  for (const score of result.conformity ?? []) {
    for (const measurement of score.measurements ?? []) {
      if (measurement.url) sources.add(byUrl.get(measurement.url) ?? `url:${measurement.url}`);
    }
  }
  return sources.size;
}

// --- Retrieval scope ---------------------------------------------------------

/** One scope dimension as the reviewer reads it, with the blocks a document value cites. */
export type ScopePart = { dimension: RunScopeDimension; text: string; blockIds: string[] };

/**
 * What the run searches for, one part per dimension in run order.
 *
 * An unset dimension stays, as "any region": nobody narrowed it, which widens the search
 * and is worth seeing before it runs. A header value is a configuration key, shown the way
 * the selector shows it; a document value is the document's own words and says where it
 * came from.
 */
export function retrievalScopeParts(scope: RetrievalScope | undefined): ScopePart[] {
  const entries = new Map((scope?.entries ?? []).map((entry) => [entry.dimension, entry]));
  return RUN_SCOPE_DIMENSIONS.flatMap((dimension) => {
    const entry = entries.get(dimension);
    if (!entry) return [];
    const text = entry.provenance === "unset" || !entry.value
      ? `any ${dimension}`
      : entry.provenance === "header"
        ? displayLabel(entry.value)
        : entry.provenance === "document"
          ? `${entry.value} (from the document)`
          : `${entry.value} (configured default)`;
    return [{ dimension, text, blockIds: entry.block_ids ?? [] }];
  });
}

// --- Identity layers ---------------------------------------------------------

/** What each identity layer partitions, in a reader's words. */
const IDENTITY_SET_LABEL: Record<IdentityReconciliation["layer"], string> = {
  document_units: "document claims",
  quantitative_targets: "numeric targets",
  insights: "insights",
  projections: "development and safety records",
};

/**
 * The sets whose duplicate check did not complete, in run order.
 *
 * A layer that fails leaves its set unmerged and the run goes on, so a duplicate there can
 * be counted twice. Derived from the records, never carried as a count beside them.
 */
export function unreconciledSets(
  reconciliations: IdentityReconciliation[] | undefined,
): string[] {
  const failed = (reconciliations ?? []).filter((record) => record.status === "not_reconciled");
  // Insight sets are one per field, so they are named once with their fields: "insights for
  // Indication, Product and Efficacy", not "insights for" again before every field.
  const fields = failed
    .filter((record) => record.layer === "insights" && record.scope)
    .map((record) => displayAttributeLabel(record.scope));
  const named = new Set<string>();
  return failed.flatMap((record) => {
    const label = record.layer === "insights" && record.scope
      ? `${IDENTITY_SET_LABEL.insights} for ${new Intl.ListFormat("en", { type: "conjunction" }).format(fields)}`
      : IDENTITY_SET_LABEL[record.layer];
    if (named.has(label)) return [];
    named.add(label);
    return [label];
  });
}

// --- Checks that could not be completed --------------------------------------

/**
 * What a run's stages could not decide, counted by what each was about.
 *
 * `not_assessed` is recorded by code when a model call failed, on whichever subject it was
 * deciding; the subject is kept and marked where it appears. This sums them for the one
 * notice that says a run is partly unread, because a result whose checks did not all run
 * must not read as a completed one. Derived from the lists, never carried beside them: a
 * stored count is a second authority that can disagree with its own list. Context
 * validation is absent - it has its own notice.
 */
export function unassessedChecks(result: {
  matches: Pick<Match, "relation">[];
  assessments: Pick<EvidenceAssessment, "strength">[];
  precedents: Pick<PrecedentSignal, "precedent">[];
  development_landscape: { target_relationship: string }[];
  safety_observations: { target_relationship: string }[];
}): { total: number; parts: string[] } {
  const counts: [number, string, string][] = [
    [result.matches.filter((item) => item.relation === "not_assessed").length,
      "evidence relation", "evidence relations"],
    [result.assessments.filter((item) => item.strength === "not_assessed").length,
      "field grounding", "field groundings"],
    [result.precedents.filter((item) => item.precedent === "not_assessed").length,
      "precedent check", "precedent checks"],
    [[...result.development_landscape, ...result.safety_observations]
      .filter((item) => item.target_relationship === "not_assessed").length,
      "record relation", "record relations"],
  ];
  return {
    total: counts.reduce((sum, [count]) => sum + count, 0),
    parts: counts
      .filter(([count]) => count > 0)
      .map(([count, singular, plural]) => countLabel(count, singular, plural)),
  };
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
  /**
   * That fact in words, phrased for how much was observed.
   *
   * "Above observed range" was said whenever the target sat past the maximum, including
   * when the minimum and the maximum were the same number. On a real run one target had
   * exactly one comparator, so the interface reported a target as above a *range* of
   * measurements when it was above a single measurement. The word claims a spread, and
   * a spread is the thing a reader is deciding whether to trust.
   */
  positionLabel: string;
  /**
   * What was observed, named for whether it spans anything.
   *
   * The same correction as `positionLabel`, in the one other place the word appears. The
   * grid drew "Observed range: 2 injections-2 injections", which is a range of nothing
   * printed twice. Three comparators can agree, so this is reachable even where the grid
   * has earned its space.
   */
  observedLabel: string;
  observedValue: string;
  meetingLabel: string;
};

export function calibrationView(conformity: Conformity, display?: NumericDisplay): CalibrationView {
  const count = conformity.benchmark_count;
  const shape: CalibrationShape = count === 0 ? "none" : count < 3 ? "compact" : "full";
  const position = targetPosition(conformity);
  return {
    shape,
    showQuartiles: count >= 4,
    showDeviation: count >= 3,
    position,
    positionLabel: positionPhrase(position, conformity, count),
    observedLabel: hasSpread(conformity) ? "Observed range" : "Observed value",
    observedValue: hasSpread(conformity)
      ? formatMeasurePair(
          conformity.benchmark_minimum,
          conformity.benchmark_maximum,
          conformity.unit,
          "\u2013",
          display,
        )
      : formatMeasure(conformity.benchmark_minimum, conformity.unit, display),
    meetingLabel:
      count > 0
        ? `${conformity.target_meeting_count} of ${count} meet target`
        : "",
  };
}

/**
 * Keyed on whether a range exists, not on how many measurements there are.
 *
 * Three identical measurements are still one value, and a reader told the target is above
 * "the observed range" would picture three points it clears rather than one it clears three
 * times. So the phrase follows the minimum and the maximum, which is what "range" names.
 */
function hasSpread(conformity: Conformity): boolean {
  return (
    conformity.benchmark_minimum != null &&
    conformity.benchmark_maximum != null &&
    conformity.benchmark_minimum !== conformity.benchmark_maximum
  );
}

function positionPhrase(
  position: CalibrationView["position"],
  conformity: Conformity,
  count: number,
): string {
  if (position === "unknown") return count === 0 ? "no comparable measurements" : "";
  if (hasSpread(conformity)) {
    return { above: "above observed range", below: "below observed range", within: "within observed range" }[
      position
    ];
  }
  // Every comparator reported the same number, so there is a value to compare with, not a
  // range. "Within" collapses to equality when the minimum and the maximum coincide.
  return { above: "above the observed value", below: "below the observed value", within: "matches the observed value" }[
    position
  ];
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
 * Coverage, not verdicts: the Fields tab already reports which targets external evidence
 * contradicts, and the priority card reads it. What nothing else reports is how much of the document stated a
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
  /* No `conflictFields` or `confirmedFields`. Which fields are contradicted is on each
     field row, with the evidence, the reason and a source link. A second list of the same
     names is a second authority on the same fact, and the weaker one. */
  unfavorableFields: string[];
  /**
   * Every field by how well evidence supports its target, summing to `fieldCount`.
   *
   * Scout was the one tool whose metrics stated no distribution, and the reason given was
   * that it has three axes over three denominators - grounding, precedent, calibration -
   * so nothing sums. That is true of the three together and false of grounding alone,
   * which every field has exactly one of.
   *
   * The buckets are `EvidenceStrength` plus one for a field the document never stated a
   * target for. Those are not `unknown`: "we looked and could not tell" and "there was
   * nothing to look at" are different answers, and folding them together would hide the
   * figure that decides whether a run is worth reading at all. `not_assessed` is a third
   * answer - the check did not run - and is kept apart from both for the same reason.
   * `not_searched` is a fourth: the reviewer left the field out of search, so the bucket
   * counts a choice made at review rather than anything the evidence did.
   */
  groundingCounts: Record<EvidenceStrength | "not_stated", number>;
  wellGroundedCount: number;
  notStatedCount: number;
  /** Fields the reviewer left out of search, which hold `not_searched` and nothing else. */
  notSearchedCount: number;
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

  const groundingCounts: Record<EvidenceStrength | "not_stated", number> = {
    well_grounded: 0, partial: 0, thin: 0, unsupported: 0, unknown: 0, no_evidence: 0,
    not_searched: 0, not_assessed: 0, not_stated: 0,
  };
  for (const row of rows) {
    // Order matters: a field with no target has no grounding to report, whatever an
    // assessment left over from an earlier state might say.
    const bucket = !(row.variable.document_target || "").trim()
      ? "not_stated"
      : row.assessment?.strength ?? "unknown";
    groundingCounts[bucket] += 1;
  }

  return {
    unfavorableFields: named((row) => row.precedent?.outcome === "unfavorable"),
    groundingCounts,
    wellGroundedCount: rows.filter((row) => row.assessment?.strength === "well_grounded")
      .length,
    // Stated by the document or not: the distinction the reader needs before reading any
    // signal, because a field with no target was never analysed.
    notStatedCount: rows.filter(
      (row) => !(row.variable.document_target || "").trim(),
    ).length,
    notSearchedCount: groundingCounts.not_searched,
    unresolvedCount: rows.filter((row) => !row.variable.target_resolved).length,
    fieldCount: rows.length,
    uncalibratedTargets: conformities.filter((item) => item.benchmark_count === 0).length,
    numericTargets: conformities.length,
  };
}
