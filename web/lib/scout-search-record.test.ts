/**
 * The record of what was searched, which the interface never showed.
 *
 * `search_plan` held 754 traces on a real run and rendered nowhere. `Sources` is per insight
 * and can only show a search that found something, so 300 of 529 distinct queries were
 * invisible: exactly the ones that make a negative verdict readable.
 */

import assert from "node:assert/strict";
import test from "node:test";

import { fieldSearchRecord, searchRecordSummary } from "./scout-search-record.ts";
import type { SearchTrace } from "./api.ts";

function trace(over: Partial<SearchTrace> = {}): SearchTrace {
  return {
    attribute_ref: "drug.indication",
    lane: "web",
    query: "a query",
    tracks: [],
    doc_block_ids: [],
    target_ids: [],
    intent_ids: [],
    input_queries: [],
    applicability: "applicable",
    applicability_reason: "",
    status: "complete",
    error: "",
    finding_count: 0,
    source_urls: [],
    ...over,
  };
}

const plan = (...traces: SearchTrace[]) => ({ search_plan: traces });

test("only this field's searches are counted", () => {
  const record = fieldSearchRecord(
    plan(trace(), trace({ attribute_ref: "drug.efficacy", query: "other" })),
    "drug.indication",
  );
  assert.equal(record.total, 1);
});

test("a lane that ran and found nothing is still reported", () => {
  // The whole point. `Sources` can only show a search that produced an insight, so a lane
  // that came back empty left no trace anywhere in the interface.
  const record = fieldSearchRecord(
    plan(trace({ lane: "pubmed", finding_count: 0 })),
    "drug.indication",
  );
  assert.equal(record.groups[0].lane, "pubmed");
  assert.equal(record.groups[0].findingCount, 0);
  assert.equal(record.completed, 1);
});

test("a lane that did not apply is counted apart from one that failed", () => {
  // One is an absence of a result, the other is a result. The excluded panel separates these
  // for the same reason.
  const record = fieldSearchRecord(
    plan(
      trace({ status: "skipped", applicability: "not_applicable", query: "a" }),
      trace({ status: "failed", error: "timeout", query: "b" }),
      trace({ query: "c" }),
    ),
    "drug.indication",
  );
  assert.equal(record.skipped, 1);
  assert.equal(record.failed, 1);
  assert.equal(record.completed, 1);
  assert.equal(record.total, 3);
});

test("one row per distinct query on a lane", () => {
  // Two intents can converge on one query. A reader counting rows is counting searches.
  const record = fieldSearchRecord(
    plan(trace({ query: "same" }), trace({ query: "same" }), trace({ query: "other" })),
    "drug.indication",
  );
  assert.equal(record.total, 2);
  assert.deepEqual(record.groups[0].searches.map((t) => t.query), ["same", "other"]);
});

test("the same query on two lanes is two searches", () => {
  // It is: two providers were asked the same question and can answer differently.
  const record = fieldSearchRecord(
    plan(trace({ lane: "web", query: "same" }), trace({ lane: "pubmed", query: "same" })),
    "drug.indication",
  );
  assert.equal(record.total, 2);
  assert.equal(record.groups.length, 2);
});

test("lanes come out in reading order, not retrieval order", () => {
  const record = fieldSearchRecord(
    plan(
      trace({ lane: "chembl", query: "a" }),
      trace({ lane: "web", query: "b" }),
      trace({ lane: "clinicaltrials", query: "c" }),
    ),
    "drug.indication",
  );
  assert.deepEqual(record.groups.map((g) => g.lane), ["web", "clinicaltrials", "chembl"]);
});

test("a lane nobody listed still appears, after the ones that are", () => {
  // Adding a lane upstream must not make it invisible here.
  const record = fieldSearchRecord(
    plan(trace({ lane: "a_new_lane", query: "a" }), trace({ lane: "web", query: "b" })),
    "drug.indication",
  );
  assert.deepEqual(record.groups.map((g) => g.lane), ["web", "a_new_lane"]);
});

test("a field with no searches says so rather than reporting zero of something", () => {
  const record = fieldSearchRecord(plan(), "drug.indication");
  assert.equal(record.total, 0);
  assert.equal(searchRecordSummary(record), "No search was planned for this field.");
});

test("the summary names only what happened", () => {
  // Nothing skipped and nothing failed is the ordinary case, and saying "0 failed" on every
  // field would say nothing.
  const clean = fieldSearchRecord(plan(trace({ query: "a" }), trace({ query: "b" })), "drug.indication");
  assert.equal(searchRecordSummary(clean), "2 searches planned.");

  const mixed = fieldSearchRecord(
    plan(
      trace({ query: "a" }),
      trace({ query: "b", status: "skipped" }),
      trace({ query: "c", status: "failed" }),
    ),
    "drug.indication",
  );
  assert.equal(searchRecordSummary(mixed), "3 searches planned · 1 not applicable · 1 failed.");
});

test("one search reads as one, not as a plural", () => {
  const one = fieldSearchRecord(plan(trace()), "drug.indication");
  assert.equal(searchRecordSummary(one), "1 search planned.");
});

test("a result saved before the plan existed reports nothing rather than throwing", () => {
  assert.equal(fieldSearchRecord({}, "drug.indication").total, 0);
});


test("the two web lanes sit beside each other", () => {
  // They are the same question asked two ways - a model that cites what it read, and a search
  // API that returns what it found - so a reader comparing them should not have to scroll
  // between them. An unlisted lane still appears, after these, so this is about order and not
  // about admission.
  const record = fieldSearchRecord(
    plan(
      trace({ lane: "pubmed", query: "a" }),
      trace({ lane: "tavily", query: "b" }),
      trace({ lane: "web", query: "c" }),
    ),
    "drug.indication",
  );
  assert.deepEqual(record.groups.map((group) => group.lane), ["web", "tavily", "pubmed"]);
});
