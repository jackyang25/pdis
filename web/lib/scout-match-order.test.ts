/**
 * Relation ordering was always deliberate; the order *inside* a relation was not.
 *
 * It fell out of retrieval order, so a 1997 paper could sit above a 2026 one. These
 * tests pin the tiebreak, and pin the two things that make it safe: undated matches
 * stay inside their own relation group, and the order is total so nothing shuffles
 * between renders.
 */

import assert from "node:assert/strict";
import test from "node:test";

import type { Finding, Match } from "./api.ts";
import {
  RELATION_ORDER,
  newestSourceDate,
  sortMatchesForReading,
} from "./scout-match-order.ts";

function finding(url: string, publishedAt: string | null): Finding {
  return {
    url,
    title: url,
    query: "q",
    retrieved_at: "2026-01-01T00:00:00+00:00",
    excerpt: null,
    published_at: publishedAt,
    source: "web",
  };
}

function match(
  relation: Match["relation"],
  statement: string,
  dates: (string | null)[],
): Match {
  return {
    relation,
    reason: "because",
    insight: {
      statement,
      query: "q",
      attribute_ref: "efficacy",
      supporting_findings: dates.map((d, i) => finding(`${statement}#${i}`, d)),
      org: null,
      source_type: null,
      intervention_class: null,
      indication: null,
    },
  };
}

const order = (matches: Match[]) =>
  sortMatchesForReading(matches).map((m) => m.insight.statement);

test("relation stays the primary key", () => {
  const matches = [
    match("unrelated", "u", ["2026-01-01T00:00:00+00:00"]),
    match("confirms", "c", ["2026-01-01T00:00:00+00:00"]),
    match("contradicts", "x", ["1997-01-01T00:00:00+00:00"]),
    match("extends", "e", ["2026-01-01T00:00:00+00:00"]),
  ];

  // The 1997 contradiction still leads three 2026 findings: recency never
  // outranks relation.
  assert.deepEqual(order(matches), ["x", "e", "c", "u"]);
});

test("newest first inside one relation", () => {
  const matches = [
    match("contradicts", "old", ["1997-09-30T00:00:00+00:00"]),
    match("contradicts", "new", ["2026-08-03T00:00:00+00:00"]),
    match("contradicts", "mid", ["2019-04-11T00:00:00+00:00"]),
  ];

  assert.deepEqual(order(matches), ["new", "mid", "old"]);
});

test("a match is as recent as its most recent supporting finding", () => {
  const m = match("confirms", "m", [
    "2011-01-25T00:00:00+00:00",
    "2024-10-22T00:00:00+00:00",
    null,
  ]);

  assert.equal(newestSourceDate(m), "2024-10-22T00:00:00+00:00");
});

test("a match with no dated source reports no date", () => {
  assert.equal(newestSourceDate(match("confirms", "m", [null, null])), null);
  assert.equal(newestSourceDate(match("confirms", "m", [])), null);
});

test("undated matches follow the dated ones within their own relation", () => {
  // Half the findings in a real run carry no date, and they cluster in the web and
  // Semantic Scholar lanes. Sinking them to the end of the list would demote those
  // two sources; containing them per relation does not.
  const matches = [
    match("confirms", "confirms-undated", [null]),
    match("contradicts", "contradicts-undated", [null]),
    match("contradicts", "contradicts-dated", ["2020-01-01T00:00:00+00:00"]),
    match("confirms", "confirms-dated", ["2026-01-01T00:00:00+00:00"]),
  ];

  assert.deepEqual(order(matches), [
    "contradicts-dated",
    "contradicts-undated",
    "confirms-dated",
    "confirms-undated",
  ]);
});

test("undated matches keep their given order", () => {
  const matches = [
    match("confirms", "first", [null]),
    match("confirms", "second", [null]),
    match("confirms", "third", [null]),
  ];

  assert.deepEqual(order(matches), ["first", "second", "third"]);
});

test("the order is total, so equal matches never shuffle", () => {
  const same = "2020-01-01T00:00:00+00:00";
  const matches = [
    match("confirms", "a", [same]),
    match("confirms", "b", [same]),
    match("confirms", "c", [same]),
  ];

  assert.deepEqual(order(matches), ["a", "b", "c"]);
  assert.deepEqual(order(sortMatchesForReading(matches)), ["a", "b", "c"]);
});

test("nothing is filtered, added, or mutated", () => {
  const matches = [
    match("confirms", "a", [null]),
    match("contradicts", "b", ["2026-01-01T00:00:00+00:00"]),
  ];
  const snapshot = structuredClone(matches);

  const sorted = sortMatchesForReading(matches);

  assert.equal(sorted.length, matches.length);
  assert.deepEqual(matches, snapshot, "the input must not be mutated");
  assert.deepEqual(
    [...sorted].map((m) => m.insight.statement).sort(),
    ["a", "b"],
  );
});

test("relation order puts the most consequential relation first", () => {
  assert.deepEqual(
    Object.entries(RELATION_ORDER).sort((a, b) => a[1] - b[1]).map(([k]) => k),
    ["contradicts", "extends", "confirms", "unrelated"],
  );
});
