/**
 * The derivations that organize a Scout result, and the one thing they must never do:
 * lose text.
 *
 * The target-row split is the risky part, because it reads a delimited string. Every test
 * on it checks the same invariant from a different angle — the cells appear verbatim in
 * the span, the span is always retained whole, and anything that does not split cleanly
 * falls back to prose rather than being shown wrong. The real documents include
 * `"injections. , Optimistic:"` with a space before the comma, which is why the guard
 * compares text and not marker spacing.
 */

import { formatMeasure, formatMeasurePair } from "./measure-format.ts";
import assert from "node:assert/strict";
import test from "node:test";

import {
  RELATION_READING_ORDER,
  calibrationView,
  distinctSourceCount,
  exclusionReasonLines,
  retrievalScopeParts,
  unreconciledSets,
  citation,
  documentTargetRows,
  documentTargetText,
  insightRegistry,
  needsFindingFallback,
  relationGroups,
  runHeadline,
  unassessedChecks,
} from "./scout-result-view.ts";
import type { Conformity, ContentBlock, Match, Variable } from "./api.ts";

// --- formatMeasure ----------------------------------------------------------

test("a unit takes a space, so a count never reads as one word", () => {
  // "1injections" and "0.6administration occasions" shipped because two formatters
  // disagreed about this.
  assert.equal(formatMeasure(1, "injections"), "1 injections");
  assert.equal(formatMeasure(0.6, "administration occasions"), "0.6 administration occasions");
});

test("percent and degree close up against the number", () => {
  assert.equal(formatMeasure(80, "%"), "80%");
  assert.equal(formatMeasure(8, "°C"), "8°C");
});

test("a unitless value is just the number, and an absent one is a dash", () => {
  assert.equal(formatMeasure(3, ""), "3");
  assert.equal(formatMeasure(null, "months"), "—");
  assert.equal(formatMeasure(Number.NaN, "months"), "—");
});

test("values round to two decimals rather than printing float noise", () => {
  assert.equal(formatMeasure(1.23456, "months"), "1.23 months");
});

// --- documentTargetRows -----------------------------------------------------

function span(quote: string, blockIds: string[] = ["b-1"]) {
  return { quote, block_ids: blockIds };
}

/** A parser-owned table row, its text and cells as Chunker records them. */
function tableRow(id: string, cells: [string, string][]): ContentBlock {
  let content = "";
  const tableCells = cells.map(([header, value], column_index) => {
    if (content) content += ", ";
    const content_start = content.length;
    content += `${header}: `;
    const value_start = content.length;
    content += value;
    return { column_index, header, value, content_start, content_end: content.length, value_start, value_end: content.length };
  });
  return {
    id, doc_id: "doc", ordinal: 0, block_type: "table_row", content, heading_stack: [], section_label: null,
    structural_meta: { column_headers: cells.map(([header]) => header), table_cells: tableCells }, style_hint: {}, image: null,
  } as ContentBlock;
}

// A real template: the column headings run to a sentence, which defeated the old marker split.
const ROW = tableRow("b-1", [
  ["Variable", "Presentation"],
  ["Minimum\nThe minimal target should be considered as a potential go/no go decision point.", "Multi-dose vial"],
  ["Optimistic\nThe optimistic target should reflect what is needed.", "Multi-dose vial"],
]);
const blocks = new Map([[ROW.id, ROW]]);

test("a whole table row is shown as its recorded cells, under the document's own headings", () => {
  const [row] = documentTargetRows([span(ROW.content)], blocks);
  assert.equal(row.kind, "table");
  if (row.kind !== "table") return;
  assert.deepEqual(row.cells.map((cell) => cell.value), ["Presentation", "Multi-dose vial", "Multi-dose vial"]);
  assert.match(row.cells[1].header, /^Minimum The minimal target/);
  assert.equal(row.cells[1].label, "Minimum");
  assert.equal(row.quote, ROW.content);
  assert.ok(ROW.content.includes("\n"), "the fixture's headings carry the template's line break");
});

test("a row quoted with its line breaks read as spaces is still that row", () => {
  const [row] = documentTargetRows([span(ROW.content.replace(/\s+/g, " "))], blocks);
  assert.equal(row.kind, "table");
});

test("part of a row, prose, or a block not held stays the document's words", () => {
  const rows = documentTargetRows([
    span("Multi-dose vial"),
    span("Under this use case, a combination of oral and LAIs…"),
    span(ROW.content, ["b-missing"]),
  ], blocks);
  assert.deepEqual(rows.map((row) => row.kind), ["prose", "prose", "prose"]);
});

test("one line of the target reads a table row by its values", () => {
  const rows = documentTargetRows([span(ROW.content), span("Plain prose.")], blocks);
  assert.equal(documentTargetText(rows), "Presentation · Multi-dose vial · Multi-dose vial Plain prose.");
});

test("one row per span, each keeping its own blocks", () => {
  // Four table rows made one paragraph before; they are four citations, not one.
  const rows = documentTargetRows([span("a", ["b-27"]), span("b", ["b-28"])]);
  assert.equal(rows.length, 2);
  assert.deepEqual(rows.map((row) => row.blockIds), [["b-27"], ["b-28"]]);
});

test("no spans yields no rows", () => {
  assert.deepEqual(documentTargetRows(undefined), []);
  assert.deepEqual(documentTargetRows([]), []);
});

// --- relations --------------------------------------------------------------

function match(relation: Match["relation"], id: string): Match {
  return {
    relation,
    reason: "",
    failure_code: relation === "not_assessed" ? "provider_error" : "",
    insight: {
      id,
      statement: `statement ${id}`,
      query: "q",
      supporting_findings: [],
      org: null,
      source_type: null,
      intervention_class: null,
      indication: null,
      attribute_ref: null,
    },
  };
}

test("decisive relations come first, then context, then off-topic", () => {
  assert.deepEqual(RELATION_READING_ORDER, ["contradicts", "confirms", "extends", "unrelated", "not_assessed"]);
});

test("the relations that settle something are listed first", () => {
  // 23 of 911 insights settled anything on a real run. Order is what points at them.
  const groups = relationGroups([
    match("unrelated", "u"),
    match("extends", "e"),
    match("confirms", "c"),
    match("contradicts", "x"),
  ]);
  assert.deepEqual(
    groups.map((group) => group.relation),
    ["contradicts", "confirms", "extends", "unrelated"],
  );
});

test("no group carries an expansion flag, so nothing can open itself", () => {
  // Every disclosure in the result view is the reader's. A flag here is how that would
  // quietly come back.
  const [group] = relationGroups([match("contradicts", "x")]);
  assert.deepEqual(Object.keys(group).sort(), ["matches", "relation"]);
});

test("a relation with nothing in it draws no group", () => {
  const groups = relationGroups([match("extends", "e")]);
  assert.deepEqual(groups.map((group) => group.relation), ["extends"]);
});

test("every match lands in exactly one group", () => {
  // Including one no relation was obtained for: a group order missing it would drop the
  // insight from the field without a trace.
  const matches = [match("extends", "a"), match("extends", "b"), match("unrelated", "c"), match("not_assessed", "d")];
  const grouped = relationGroups(matches).flatMap((group) => group.matches);
  assert.equal(grouped.length, matches.length);
});

// --- the registry and citations ---------------------------------------------

test("an insight is registered once however often it is cited", () => {
  const matches = [match("extends", "a"), match("confirms", "b")];
  const registry = insightRegistry(matches);
  assert.equal(registry.byId.size, 2);
});

test("a citation resolves ids into the shared pool", () => {
  // The mechanism that removed 937 redundant renders: signals point, they do not copy.
  const registry = insightRegistry([match("extends", "a"), match("confirms", "b")]);
  const cited = citation(["a", "b"], registry);
  assert.equal(cited.resolved.length, 2);
  assert.equal(cited.unresolvedCount, 0);
  assert.equal(cited.total, 2);
});

test("a repeated id is counted once", () => {
  const registry = insightRegistry([match("extends", "a")]);
  assert.equal(citation(["a", "a"], registry).total, 1);
});

test("an id naming nothing is reported, not swallowed", () => {
  // A citation that silently resolves to nothing is how a reader comes to believe a
  // verdict rests on evidence that is not there.
  const registry = insightRegistry([match("extends", "a")]);
  const cited = citation(["a", "ghost"], registry);
  assert.equal(cited.resolved.length, 1);
  assert.equal(cited.unresolvedCount, 1);
});

test("the finding fallback is needed exactly when nothing resolved", () => {
  // `assessment.supporting_findings` lives nowhere else in the result, so this is the one
  // path where deduplicating by reference could have deleted citations.
  const registry = insightRegistry([match("extends", "a")]);
  assert.equal(needsFindingFallback(citation(["a"], registry)), false);
  assert.equal(needsFindingFallback(citation(["ghost"], registry)), true);
  assert.equal(needsFindingFallback(citation([], registry)), true);
});

// --- calibration ------------------------------------------------------------

function conformity(overrides: Partial<Conformity> = {}): Conformity {
  return {
    attribute_refs: ["drug.efficacy"],
    target_id: "t1",
    target_role: "threshold",
    target_value: 4,
    comparator: "<=",
    unit: "injections",
    target_label: "",
    target_quote: "",
    target_meeting_count: 0,
    target_meeting_rate: 0,
    verdict: "",
    benchmark_count: 0,
    benchmark_minimum: null,
    benchmark_maximum: null,
    benchmark_mean: null,
    benchmark_median: null,
    benchmark_lower_quartile: null,
    benchmark_upper_quartile: null,
    benchmark_standard_deviation: null,
    target_percentile: null,
    ambition_percentile: null,
    calibration_status: "insufficient",
    measurements: [],
    excluded_measurements: [],
    source_dispositions: [],
    ...overrides,
  };
}

test("no comparators earns no grid and no chart", () => {
  // 10 of 12 targets on a real run. The interface built a six-cell grid for it anyway.
  const view = calibrationView(conformity({ benchmark_count: 0 }));
  assert.equal(view.shape, "none");
  assert.equal(view.showQuartiles, false);
  assert.equal(view.showDeviation, false);
});

test("one or two comparators earn a compact line, not a grid", () => {
  assert.equal(calibrationView(conformity({ benchmark_count: 1 })).shape, "compact");
  assert.equal(calibrationView(conformity({ benchmark_count: 2 })).shape, "compact");
});

test("the grid appears at three, where an SD exists", () => {
  const view = calibrationView(conformity({ benchmark_count: 3 }));
  assert.equal(view.shape, "full");
  assert.equal(view.showDeviation, true);
  assert.equal(view.showQuartiles, false);
});

test("quartiles wait for four, mirroring the backend's own threshold", () => {
  assert.equal(calibrationView(conformity({ benchmark_count: 4 })).showQuartiles, true);
});

test("the target's position is the decisive fact and is derived, not asserted", () => {
  const base = { benchmark_count: 3, benchmark_minimum: 1, benchmark_maximum: 2 };
  assert.equal(calibrationView(conformity({ ...base, target_value: 4 })).position, "above");
  assert.equal(calibrationView(conformity({ ...base, target_value: 0 })).position, "below");
  assert.equal(calibrationView(conformity({ ...base, target_value: 1.5 })).position, "within");
  assert.equal(calibrationView(conformity({ benchmark_count: 0 })).position, "unknown");
});

test("the meeting label carries both halves or says nothing", () => {
  assert.equal(
    calibrationView(conformity({ benchmark_count: 3, target_meeting_count: 3 })).meetingLabel,
    "3 of 3 meet target",
  );
  assert.equal(calibrationView(conformity({ benchmark_count: 0 })).meetingLabel, "");
});

test("a range is only called a range when there is one", () => {
  // The case that prompted this: one target on a real run had a single comparator, so the
  // minimum and the maximum were the same number and the row still read "above observed
  // range". A reader deciding whether to trust a target reads that as a spread it clears.
  const one = calibrationView(
    conformity({
      benchmark_count: 1,
      benchmark_minimum: 1,
      benchmark_maximum: 1,
      target_value: 4,
    }),
  );
  assert.equal(one.position, "above");
  assert.equal(one.positionLabel, "above the observed value");

  // Keyed on the range, not the count: three measurements that agree are still one value.
  const agreeing = calibrationView(
    conformity({
      benchmark_count: 3,
      benchmark_minimum: 2,
      benchmark_maximum: 2,
      target_value: 1,
    }),
  );
  assert.equal(agreeing.positionLabel, "below the observed value");

  // And "within" collapses to equality when there is nothing to be within.
  assert.equal(
    calibrationView(
      conformity({
        benchmark_count: 2,
        benchmark_minimum: 5,
        benchmark_maximum: 5,
        target_value: 5,
      }),
    ).positionLabel,
    "matches the observed value",
  );
});

test("the grid names what was observed the same way the row does", () => {
  // The one other place the word appeared. Three comparators can all report the same number,
  // so this is reachable even where the grid has earned its space, and it printed a range of
  // nothing as "2 injections-2 injections".
  const agreeing = calibrationView(
    conformity({
      benchmark_count: 3,
      benchmark_minimum: 2,
      benchmark_maximum: 2,
      unit: "injections",
    }),
  );
  assert.equal(agreeing.observedLabel, "Observed value");
  assert.equal(agreeing.observedValue, "2 injections");

  const spread = calibrationView(
    conformity({
      benchmark_count: 3,
      benchmark_minimum: 1,
      benchmark_maximum: 2,
      unit: "injections",
    }),
  );
  assert.equal(spread.observedLabel, "Observed range");
  // The unit once, not on each end. "1 injections-2 injections" spent most of the cell on
  // the unit and buried the two numbers that are the content.
  assert.equal(spread.observedValue, "1\u20132 injections");
});

test("a pair of numbers states its unit once", () => {
  assert.equal(formatMeasurePair(1, 2, "injections", "\u2013"), "1\u20132 injections");
  assert.equal(formatMeasurePair(1.33, 0.58, "administration occasions", " \u00b7 "),
    "1.33 \u00b7 0.58 administration occasions");
  // A unit that closes up stays closed up on the end that carries it.
  assert.equal(formatMeasurePair(20, 80, "%", "\u2013"), "20\u201380%");
});

test("a missing end formats separately, so the placeholder cannot borrow a unit", () => {
  // "\u2014-2 injections" would read as one value with a unit rather than as one value
  // missing, which is the case a reader has to notice.
  assert.equal(formatMeasurePair(null, 2, "injections", "\u2013"), "\u2014\u20132 injections");
  assert.equal(formatMeasurePair(1, null, "injections", "\u2013"), "1 injections\u2013\u2014");
  assert.equal(formatMeasurePair(null, null, "injections", "\u2013"), "\u2014\u2013\u2014");
});

test("one rule decides both, so they cannot disagree", () => {
  // The row and the grid describe the same two numbers. Deciding separately is how one comes
  // to say "range" while the other says "value" about the same target.
  for (const [min, max] of [[1, 1], [1, 2], [5, 5]] as const) {
    const view = calibrationView(
      conformity({ benchmark_count: 3, benchmark_minimum: min, benchmark_maximum: max, target_value: 9 }),
    );
    const rowSaysRange = view.positionLabel.includes("range");
    const gridSaysRange = view.observedLabel === "Observed range";
    assert.equal(rowSaysRange, gridSaysRange, `disagreed at ${min}-${max}`);
  }
});

test("a real spread still reads as a range", () => {
  assert.equal(
    calibrationView(
      conformity({
        benchmark_count: 3,
        benchmark_minimum: 1,
        benchmark_maximum: 2,
        target_value: 2,
      }),
    ).positionLabel,
    "within observed range",
  );
  assert.equal(
    calibrationView(
      conformity({
        benchmark_count: 3,
        benchmark_minimum: 1,
        benchmark_maximum: 2,
        target_value: 9,
      }),
    ).positionLabel,
    "above observed range",
  );
});

test("no comparators says so, and says it once", () => {
  // The page used to branch on the shape to pick between this phrase and a position, which
  // put the choice in two places. The phrase comes from here, like `meetingLabel`.
  const none = calibrationView(conformity({ benchmark_count: 0 }));
  assert.equal(none.position, "unknown");
  assert.equal(none.positionLabel, "no comparable measurements");
});

// --- the run headline -------------------------------------------------------

function variable(name: string, overrides: Partial<Variable> = {}): Variable {
  return {
    name,
    description: "",
    document_target: "a stated target",
    document_spans: [],
    definition_mode: "fixed",
    target_resolved: true,
    target_resolution_reason: "",
    evidence_domain: "clinical",
    supplies_scope: "",
    entities: [],
    quantitative_target_ids: [],
    quantitative_statement_dispositions: [],
    quantitative_target_status: "not_applicable",
    quantitative_target_status_reason: "",
    ...overrides,
  };
}

function row(name: string, overrides: Record<string, unknown> = {}) {
  return {
    variable: variable(name),
    matches: [] as Match[],
    assessment: null,
    precedent: null,
    conformities: [] as Conformity[],
    ...overrides,
  } as Parameters<typeof runHeadline>[0][number];
}

test("coverage reports no verdicts, because the field rows already do", () => {
  // Naming the contradicting fields here duplicated the field rows directly below, which
  // report them with evidence and a source link.
  const headline = runHeadline([
    row("drug.efficacy", { matches: [match("contradicts", "x"), match("confirms", "c")] }),
  ]);
  assert.equal("conflictFields" in headline, false);
  assert.equal("confirmedFields" in headline, false);
});

test("a field with no stated target counts as not stated, not as clean", () => {
  const headline = runHeadline([
    row("drug.cogs", { variable: variable("drug.cogs", { document_target: "" }) }),
    row("drug.efficacy"),
  ]);
  assert.equal(headline.notStatedCount, 1);
  assert.equal(headline.fieldCount, 2);
});

test("a field whose grounding was not assessed has its own bucket, not unknown", () => {
  // "We looked and could not tell" and "the check did not run" are different answers, and
  // the counts still have to sum to the fields.
  const headline = runHeadline([
    row("drug.efficacy", {
      assessment: {
        attribute_ref: "drug.efficacy", strength: "not_assessed", reason: "", doc_target: "",
        doc_block_ids: [], supporting_insight_ids: [], supporting_findings: [],
        failure_code: "response_truncated",
      },
    }),
    row("drug.safety"),
  ]);
  assert.equal(headline.groundingCounts.not_assessed, 1);
  assert.equal(headline.groundingCounts.unknown, 1);
  assert.equal(
    Object.values(headline.groundingCounts).reduce((sum, count) => sum + count, 0),
    headline.fieldCount,
  );
});

test("a field left out at review has its own bucket, and the buckets still sum", () => {
  const headline = runHeadline([
    row("drug.efficacy", {
      assessment: {
        attribute_ref: "drug.efficacy", strength: "not_searched", reason: "", doc_target: "",
        doc_block_ids: [], supporting_insight_ids: [], supporting_findings: [], failure_code: "",
      },
    }),
    row("drug.safety"),
  ]);
  assert.equal(headline.groundingCounts.not_searched, 1);
  assert.equal(headline.notSearchedCount, 1);
  assert.equal(
    Object.values(headline.groundingCounts).reduce((sum, count) => sum + count, 0),
    headline.fieldCount,
  );
});

test("an unfavourable precedent is named, since it is one of 18", () => {
  const headline = runHeadline([
    row("drug.safety", {
      precedent: {
        attribute_ref: "drug.safety",
        precedent: "direct",
        outcome: "unfavorable",
        reason: "",
        doc_block_ids: [],
        coverage_insight_ids: [],
        outcome_insight_ids: [],
        supporting_insight_ids: [],
        supporting_findings: [],
        failure_code: "",
      },
    }),
  ]);
  assert.deepEqual(headline.unfavorableFields, ["drug.safety"]);
});

test("uncalibrated targets are counted against the total", () => {
  const headline = runHeadline([
    row("drug.efficacy", {
      conformities: [conformity({ benchmark_count: 0 }), conformity({ benchmark_count: 3 })],
    }),
  ]);
  assert.equal(headline.numericTargets, 2);
  assert.equal(headline.uncalibratedTargets, 1);
});

test("a check reads apart from a judgment", () => {
  const lines = exclusionReasonLines({
    semantic_status: "unknown",
    semantic_reason: "Regimen compatibility is unknown: the quote omits the spacing.",
    structural_reasons: ["The source states a range, not a single number to compare."],
    exclusion_reasons: [
      "Regimen compatibility is unknown: the quote omits the spacing.",
      "The source states a range, not a single number to compare.",
    ],
  });
  assert.deepEqual(lines.checks, ["The source states a range, not a single number to compare."]);
  assert.equal(lines.judgment, "Regimen compatibility is unknown: the quote omits the spacing.");
  assert.deepEqual(lines.other, [], "a reason was shown twice");
});

test("an older result does not show its judgment twice", () => {
  // The bug this closes. Before `structural_reasons` existed the reason was stored with a
  // "semantic status: X - " prefix, so matching on equality left the prefixed copy in the
  // leftovers and the reason rendered once cleanly and once again inside them.
  const reason = "Regimen compatibility is unknown: the quote omits the spacing.";
  const lines = exclusionReasonLines({
    semantic_status: "unknown",
    semantic_reason: reason,
    exclusion_reasons: [
      `semantic status: unknown — ${reason}`,
      "numeric expression is range, not an atomic scalar",
      "numeric expression is range, not an atomic scalar",
    ],
  });
  assert.equal(lines.judgment, reason);
  // The old duplicate collapses too, and the check survives as an unattributed leftover
  // rather than being dropped: an older file cannot say which kind it was.
  assert.deepEqual(lines.other, ["numeric expression is range, not an atomic scalar"]);
});

test("a comparable measurement claims no judgment", () => {
  // Excluded for a structural reason alone. Its semantic reason, if any, is not a cause.
  const lines = exclusionReasonLines({
    semantic_status: "comparable",
    semantic_reason: "Every dimension matches.",
    structural_reasons: ["The source measures in fraction, and the target is in %."],
    exclusion_reasons: ["The source measures in fraction, and the target is in %."],
  });
  assert.equal(lines.judgment, "");
  assert.deepEqual(lines.other, []);
});

test("a reviewer's own words survive as their own line", () => {
  const lines = exclusionReasonLines({
    semantic_status: "comparable",
    structural_reasons: [],
    exclusion_reasons: ["a reviewer rejected this measurement"],
  });
  assert.deepEqual(lines.other, ["a reviewer rejected this measurement"]);
});

test("a measurement with nothing recorded produces nothing", () => {
  assert.deepEqual(exclusionReasonLines({}), { checks: [], judgment: "", other: [] });
});

// --- checks that could not be completed --------------------------------------

test("every check a stage could not complete is counted by what it was about", () => {
  // A run with failed checks must not read as a completed one, and the count is derived
  // from the lists themselves rather than carried beside them.
  const failed = { failure_code: "provider_error" as const };
  const checks = unassessedChecks({
    matches: [match("not_assessed", "a"), match("not_assessed", "b"), match("extends", "c")],
    assessments: [{ strength: "not_assessed" }, { strength: "thin" }],
    precedents: [{ precedent: "not_assessed", ...failed }, { precedent: "direct" }],
    development_landscape: [{ target_relationship: "not_assessed" }],
    safety_observations: [{ target_relationship: "unrelated" }, { target_relationship: "not_assessed" }],
  });
  assert.deepEqual(checks.parts, [
    "2 evidence relations",
    "1 field grounding",
    "1 precedent check",
    "2 record relations",
  ]);
  assert.equal(checks.total, 6);
});

test("a run whose checks all completed reports nothing", () => {
  const checks = unassessedChecks({
    matches: [match("unrelated", "a")],
    assessments: [{ strength: "unknown" }],
    precedents: [{ precedent: "unknown" }],
    development_landscape: [{ target_relationship: "unknown" }],
    safety_observations: [],
  });
  assert.equal(checks.total, 0);
  assert.deepEqual(checks.parts, []);
});

test("a source is counted once per record, however many links reached it", () => {
  // Keyed by record identity, and by URL only where a saved finding states none. Two pages
  // for one trial are one source; a measurement is counted through the finding it came from.
  const finding = (url: string, record_key?: string) => ({
    url, title: "T", query: "q", retrieved_at: "", excerpt: null, published_at: null, source: "pubmed",
    ...(record_key ? { record_key } : {}),
  });
  const result = {
    matches: [
      { insight: { supporting_findings: [finding("https://a.test/1", "pubmed:1"), finding("https://a.test/1-mirror", "pubmed:1")] } },
      { insight: { supporting_findings: [finding("https://b.test/", ""), finding("https://b.test/")] } },
    ],
    assessments: [{ supporting_findings: [finding("https://a.test/1", "pubmed:1")] }],
    precedents: [],
    conformity: [{ measurements: [{ url: "https://a.test/1-mirror" }, { url: "https://c.test/" }] }],
    development_landscape: [],
    safety_observations: [],
  } as unknown as Parameters<typeof distinctSourceCount>[0];
  assert.equal(distinctSourceCount(result), 3);
});

test("the search scope names every dimension, and which ones nobody narrowed", () => {
  // Unset is a deliberate widening, not a gap, so it reads as "any region" rather than
  // disappearing; a document-derived value says so and keeps the blocks it was read from.
  const parts = retrievalScopeParts({ entries: [
    { dimension: "region", value: "Kenya", provenance: "document", block_ids: ["doc/b-3"] },
    { dimension: "condition", value: "tuberculosis", provenance: "header", block_ids: [] },
    { dimension: "intervention", value: "", provenance: "unset", block_ids: [] },
  ] });
  assert.deepEqual(parts, [
    { dimension: "condition", text: "Tuberculosis", blockIds: [] },
    { dimension: "intervention", text: "any intervention", blockIds: [] },
    { dimension: "region", text: "Kenya (from the document)", blockIds: ["doc/b-3"] },
  ]);
  assert.equal(
    retrievalScopeParts({ entries: [{ dimension: "region", value: "Sub-Saharan Africa", provenance: "config_default", block_ids: [] }] })[0].text,
    "Sub-Saharan Africa (configured default)",
  );
  assert.deepEqual(retrievalScopeParts(undefined), []);
});

test("a set whose duplicates were not merged is named, and only that set", () => {
  // `not_reconciled` means the identity call failed and the set went on unmerged, so its
  // duplicates may be counted separately. A layer that merged nothing decided that.
  const record = (layer: "document_units" | "quantitative_targets" | "insights" | "projections", status: "reconciled" | "not_reconciled", scope = "") =>
    ({ layer, scope, status, items: 3, merged: 0, failure_code: status === "not_reconciled" ? "provider_error" as const : "" as const, reason: "" });
  assert.deepEqual(unreconciledSets([
    record("document_units", "reconciled"),
    record("quantitative_targets", "not_reconciled"),
    record("insights", "not_reconciled", "vaccine.dose_volume"),
    record("insights", "not_reconciled", "vaccine.efficacy"),
    record("projections", "not_reconciled"),
  ]), ["numeric targets", "insights for Dose volume and Efficacy", "development and safety records"]);
  assert.deepEqual(unreconciledSets([record("insights", "reconciled", "x")]), []);
  assert.deepEqual(unreconciledSets(undefined), []);
});
