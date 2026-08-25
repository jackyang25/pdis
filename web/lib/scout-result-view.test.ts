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

import assert from "node:assert/strict";
import test from "node:test";

import {
  RELATION_READING_ORDER,
  calibrationView,
  exclusionReasonLines,
  formatMeasurePair,
  citation,
  documentTargetRows,
  formatMeasure,
  insightRegistry,
  needsFindingFallback,
  relationGroups,
  runHeadline,
} from "./scout-result-view.ts";
import type { Conformity, Match, Variable } from "./api.ts";

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

const REAL_ROW =
  "Variable: Product, Minimum: Long-acting injectable (LAI) with oral run-in, ≤ 3mL per " +
  "injection, LAI administration of ≤4 injections. , Optimistic: A one-time LAI, ≤3mL per " +
  "injection, single injection containing 3-4 drugs";

test("a table row splits into its three cells", () => {
  const [row] = documentTargetRows([span(REAL_ROW)]);
  assert.equal(row.kind, "bounded");
  if (row.kind !== "bounded") return;
  assert.equal(row.variable, "Product");
  assert.match(row.minimum, /^Long-acting injectable/);
  assert.match(row.optimistic, /^A one-time LAI/);
});

test("a space before the comma does not defeat the split", () => {
  // The real documents contain "injections. , Optimistic:". A guard that compared
  // reassembled marker spacing rejected this and fell back to a 995-character paragraph.
  const [row] = documentTargetRows([span(REAL_ROW)]);
  assert.equal(row.kind, "bounded");
});

test("every cell appears verbatim inside its own span", () => {
  // The invariant that makes the split faithful rather than clever.
  const [row] = documentTargetRows([span(REAL_ROW)]);
  if (row.kind !== "bounded") throw new Error("expected a bounded row");
  for (const cell of [row.variable, row.minimum, row.optimistic]) {
    assert.ok(REAL_ROW.includes(cell), `${cell.slice(0, 40)}… is not in the span`);
  }
});

test("the span is retained whole on every row, split or not", () => {
  const rows = documentTargetRows([span(REAL_ROW), span("Plain prose about adherence.")]);
  assert.deepEqual(rows.map((row) => row.quote), [REAL_ROW, "Plain prose about adherence."]);
});

test("prose that is not a table row stays prose", () => {
  const [row] = documentTargetRows([span("Under this use case, a combination of oral and LAIs…")]);
  assert.equal(row.kind, "prose");
});

test("a partial marker set falls back to prose rather than guessing", () => {
  const rows = documentTargetRows([
    span("Variable: Product, Minimum: something, but no optimistic marker"),
    span("Minimum: 3 years, Optimistic: 5 years"),
    span("Variable: , Minimum: , Optimistic: "),
  ]);
  assert.deepEqual(rows.map((row) => row.kind), ["prose", "prose", "prose"]);
});

test("text after the last marker is kept, not truncated", () => {
  const rows = documentTargetRows([
    span("Variable: A, Minimum: one, Optimistic: two, and a trailing clause"),
  ]);
  const row = rows[0];
  assert.equal(row.kind, "bounded");
  if (row.kind !== "bounded") return;
  assert.equal(row.optimistic, "two, and a trailing clause");
});

test("one row per span, each keeping its own blocks", () => {
  // Four table rows made one paragraph before; they are four citations, not one.
  const rows = documentTargetRows([
    span("Variable: Product, Minimum: a, Optimistic: b", ["b-27"]),
    span("Variable: Duration, Minimum: c, Optimistic: d", ["b-28"]),
  ]);
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
  assert.deepEqual(RELATION_READING_ORDER, ["contradicts", "confirms", "extends", "unrelated"]);
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
  const matches = [match("extends", "a"), match("extends", "b"), match("unrelated", "c")];
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

test("coverage reports no verdicts, because Priorities already does", () => {
  // Naming the contradicting fields here duplicated `selectScoutPriorities`' first tier,
  // directly above the panel that reports them with evidence and a source link.
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
