import assert from "node:assert/strict";
import test from "node:test";

import { buildComparatorDistribution } from "./comparator-distribution.ts";

const measurement = (value: number, unit = "%") => ({
  value,
  unit,
  expressionKind: "point_estimate",
  source_quote: `Observed ${value}${unit}`,
  source_record_id: `record-${value}-${unit}`,
  source_identity_status: "canonical",
  semantic_status: "contextual",
  title: "A cited paper",
});

test("builds a padded distribution containing comparators and target", () => {
  const model = buildComparatorDistribution({
    targetValue: 80,
    unit: "%",
    minimum: 60,
    maximum: 90,
    median: 75,
    lowerQuartile: 68,
    upperQuartile: 84,
    included: [measurement(60), measurement(75), measurement(90)],
    excluded: [measurement(55)],
  });

  assert.ok(model);
  assert.equal(model.included.length, 3);
  assert.equal(model.excluded.length, 1);
  assert.ok(model.domainMinimum < 55);
  assert.ok(model.domainMaximum > 90);
  assert.ok(model.lowerQuartileX < model.medianX);
  assert.ok(model.medianX < model.upperQuartileX);
});

test("keeps incompatible excluded measurements out of the plot", () => {
  const model = buildComparatorDistribution({
    targetValue: 80,
    unit: "%",
    minimum: 70,
    maximum: 90,
    median: 80,
    lowerQuartile: 75,
    upperQuartile: 85,
    included: [measurement(70), measurement(90)],
    excluded: [measurement(12, "months")],
  });

  assert.ok(model);
  assert.equal(model.excluded.length, 0);
  assert.equal(model.unplottableExcludedCount, 1);
});

test("does not plot a contextual bound as an exact point", () => {
  const bound = {
    ...measurement(90),
    expressionKind: "bound",
  };
  const model = buildComparatorDistribution({
    targetValue: 80,
    unit: "%",
    minimum: null,
    maximum: null,
    median: null,
    lowerQuartile: null,
    upperQuartile: null,
    included: [],
    excluded: [bound],
  });

  assert.equal(model, null);
});

test("uses a non-zero domain for a single repeated value", () => {
  const model = buildComparatorDistribution({
    targetValue: 50,
    unit: "%",
    minimum: 50,
    maximum: 50,
    median: 50,
    lowerQuartile: 50,
    upperQuartile: 50,
    included: [measurement(50)],
    excluded: [],
  });

  assert.ok(model);
  assert.ok(model.domainMaximum > model.domainMinimum);
  assert.equal(model.targetX, 50);
});

test("plots related context even when none qualify for statistics", () => {
  const excluded = {
    ...measurement(75),
  };
  const model = buildComparatorDistribution({
    targetValue: 80,
    unit: "%",
    minimum: null,
    maximum: null,
    median: null,
    lowerQuartile: null,
    upperQuartile: null,
    included: [],
    excluded: [excluded],
  });

  assert.ok(model);
  assert.equal(model.included.length, 0);
  assert.equal(model.excluded.length, 1);
  assert.ok(model.excluded[0].x < model.targetX);
});

test("does not render an empty comparator cohort", () => {
  assert.equal(buildComparatorDistribution({
    targetValue: 50,
    unit: "%",
    minimum: null,
    maximum: null,
    median: null,
    lowerQuartile: null,
    upperQuartile: null,
    included: [],
    excluded: [],
  }), null);
});

test("unit comparison matches the server's normalization", () => {
  // conformity._unit_key strips ALL whitespace and folds the fraction slash, so
  // a contextual value the server treats as same-unit must still be plotted.
  const model = buildComparatorDistribution({
    targetValue: 50,
    unit: "mg/dose",
    minimum: null,
    maximum: null,
    median: null,
    lowerQuartile: null,
    upperQuartile: null,
    included: [],
    excluded: [
      { ...measurement(40, "mg / dose"), semantic_status: "contextual" },
      { ...measurement(60, "MG⁄DOSE"), semantic_status: "contextual" },
    ],
  });

  assert.ok(model);
  assert.equal(model.excluded.length, 2);
  assert.equal(model.unplottableExcludedCount, 0);
});
