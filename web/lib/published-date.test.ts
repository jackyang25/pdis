import assert from "node:assert/strict";
import test from "node:test";

import { formatPublishedMonth } from "./published-date.ts";

test("a publication date reads to the month, and an unreadable one reads as none", () => {
  assert.equal(formatPublishedMonth("2024-03-15"), "Mar 2024");
  assert.equal(formatPublishedMonth(""), null);
  assert.equal(formatPublishedMonth(null), null);
  assert.equal(formatPublishedMonth("sometime in spring"), null);
});

test("a date reads only as precisely as the source stated it", () => {
  // A year-only date is held as 1 January; shown to the month it claimed a January it never stated.
  assert.equal(formatPublishedMonth("2024-01-01T00:00:00+00:00", "year"), "2024");
  assert.equal(formatPublishedMonth("2024-03-01T00:00:00+00:00", "month"), "Mar 2024");
  // Read in UTC: the first of a month west of Greenwich was showing as the month before.
  assert.equal(formatPublishedMonth("2024-03-01T00:00:00+00:00"), "Mar 2024");
});
