import assert from "node:assert/strict";
import test from "node:test";
import { formatMeasure, formatMeasurePair } from "./scout-result-view.ts";

test("explicit presentation formats years and quantities without guessing from magnitude", () => {
  const year = { kind: "calendar_year" as const, unit_singular: "", unit_plural: "" };
  const dose = { kind: "quantity" as const, unit_singular: "dose", unit_plural: "doses" };
  assert.equal(formatMeasure(2027, "calendar year", year), "2027");
  assert.equal(formatMeasure(1, "doses", dose), "1 dose");
  assert.equal(formatMeasure(2, "doses", dose), "2 doses");
  assert.equal(formatMeasurePair(2026, 2027, "calendar year", "–", year), "2026–2027");
  assert.equal(formatMeasurePair(1, 2, "doses", "–", dose), "1–2 doses");
  assert.equal(formatMeasure(2027, "doses", dose), `${(2027).toLocaleString()} doses`);
  assert.equal(formatMeasure(0.005, "%"), "0.005%");
  assert.equal(formatMeasure(null, "doses", dose), "—");
});
