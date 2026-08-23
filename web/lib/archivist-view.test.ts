/**
 * How an Archivist answer reads: what collapses into one row, and what never does.
 *
 * The interesting cases are the ones that look like duplicates and are not. "24 months"
 * as a minimum and "24 months" as an optimum share a number and make different claims;
 * "2 years" and "24 months" describe the same span in words no reader should see merged,
 * because merging them would show a number neither document wrote.
 */

import assert from "node:assert/strict";
import test from "node:test";

import {
  answeredOf,
  attributeLabel,
  attributeTotals,
  collapseValues,
  documentTitle,
  fenceSummary,
  filterableColumns,
} from "./archivist-view.ts";
import type {
  ArchivistColumn,
  ArchivistRecord,
  ArchivistSourceTypeGroup,
} from "./api.ts";

function record(overrides: Partial<ArchivistRecord> = {}): ArchivistRecord {
  return {
    document_id: "d1",
    attribute: "vaccine.shelf_life",
    status: "stated",
    bound: "single",
    stated: "24 months",
    magnitude: 24,
    unit: "months",
    tags: [],
    condition_attribute: "",
    condition_stated: "",
    quote: "at least 24 months",
    block_id: "b1",
    block_text: "Stable for at least 24 months.",
    section_label: "stability",
    reason: "",
    ...overrides,
  };
}

test("a qualified attribute name reads as a label", () => {
  assert.equal(attributeLabel("vaccine.shelf_life"), "Shelf Life");
  assert.equal(attributeLabel("vaccine.duration_of_protection"), "Duration Of Protection");
});

test("an unqualified name still reads", () => {
  assert.equal(attributeLabel("shelf_life"), "Shelf Life");
});

test("two documents giving the same answer collapse into one row", () => {
  const collapsed = collapseValues([
    record({ document_id: "d1" }),
    record({ document_id: "d2" }),
  ]);
  assert.equal(collapsed.length, 1);
  assert.equal(collapsed[0].records.length, 2);
});

test("a minimum and an optimum of the same number stay two rows", () => {
  // They share a number and make different claims. Collapsing them would report one
  // target where the document set two.
  const collapsed = collapseValues([
    record({ bound: "minimum" }),
    record({ bound: "optimal" }),
  ]);
  assert.deepEqual(
    collapsed.map((value) => value.bound),
    ["minimum", "optimal"],
  );
});

test("the same span written two ways stays two rows", () => {
  // Grouped on the document's own words, never on the parsed magnitude. The parse exists
  // to sort within a unit, not to decide what counts as the same answer.
  const collapsed = collapseValues([
    record({ stated: "24 months", magnitude: 24, unit: "months" }),
    record({ document_id: "d2", stated: "2 years", magnitude: 2, unit: "years" }),
  ]);
  assert.equal(collapsed.length, 2);
});

test("one value per condition, even when the number is identical", () => {
  const collapsed = collapseValues([
    record({}),
    record({
      condition_attribute: "vaccine.presentation",
      condition_stated: "lyophilized",
    }),
  ]);
  assert.equal(collapsed.length, 2);
});

test("values sort by bound, then by the number where there is one", () => {
  const collapsed = collapseValues([
    record({ bound: "single", stated: "36 months", magnitude: 36 }),
    record({ bound: "optimal", stated: "48 months", magnitude: 48 }),
    record({ bound: "minimum", stated: "24 months", magnitude: 24 }),
    record({ bound: "single", stated: "12 months", magnitude: 12 }),
  ]);
  assert.deepEqual(
    collapsed.map((value) => value.stated),
    ["24 months", "48 months", "12 months", "36 months"],
  );
});

test("a value that did not parse sorts after one that did", () => {
  // Rather than being ordered against a number it does not have.
  const collapsed = collapseValues([
    record({ stated: "24 to 36 months", magnitude: null, unit: "" }),
    record({ stated: "18 months", magnitude: 18 }),
  ]);
  assert.deepEqual(
    collapsed.map((value) => value.stated),
    ["18 months", "24 to 36 months"],
  );
});

function group(
  overrides: Partial<ArchivistSourceTypeGroup> = {},
): ArchivistSourceTypeGroup {
  return { source_type: "itpp", values: [], uncertain: [], silent: [], ...overrides };
}

test("the denominator counts every document asked, not only those that answered", () => {
  // Three of four is a convention; three of nineteen is an outlier. A numerator alone
  // invites the reader to supply the denominator themselves.
  const counted = answeredOf(
    group({
      values: [record({ document_id: "d1" }), record({ document_id: "d2" })],
      uncertain: [record({ document_id: "d3" })],
      silent: ["d4", "d5"],
    }),
  );
  assert.deepEqual(counted, { answered: 2, total: 5 });
});

test("a document with two bounds counts once", () => {
  const counted = answeredOf(
    group({
      values: [record({ bound: "minimum" }), record({ bound: "optimal" })],
    }),
  );
  assert.deepEqual(counted, { answered: 1, total: 1 });
});

test("an attribute total sums its document types without merging them", () => {
  const totals = attributeTotals({
    attribute: "vaccine.shelf_life",
    quantity: "duration",
    tag_vocabulary: [],
    groups: [
      group({ source_type: "itpp", values: [record()], silent: ["d2"] }),
      group({ source_type: "ctpp", values: [record({ document_id: "d3" })] }),
    ],
  });
  assert.deepEqual(totals, { answered: 2, total: 3 });
});

function column(overrides: Partial<ArchivistColumn> = {}): ArchivistColumn {
  return {
    attribute: "vaccine.shelf_life",
    tags: [],
    quantity: "duration",
    not_confused_with: [],
    ...overrides,
  };
}

test("a column is filterable exactly when it publishes a vocabulary", () => {
  const columns = [
    column({ attribute: "vaccine.shelf_life", tags: [] }),
    column({ attribute: "vaccine.target_population", tags: ["infants"] }),
  ];
  assert.deepEqual(
    filterableColumns(columns).map((item) => item.attribute),
    ["vaccine.target_population"],
  );
});

test("the fence reads as a sentence, and says nothing when there is none", () => {
  assert.equal(
    fenceSummary(column({ not_confused_with: ["vaccine.thermostability"] })),
    "Kept separate from Thermostability.",
  );
  assert.equal(fenceSummary(column()), "");
});

test("a document id with no matching document falls back to the id", () => {
  // Rather than rendering an empty string, which would read as a document with no name.
  assert.equal(documentTitle([], "mal-itpp"), "mal-itpp");
});
