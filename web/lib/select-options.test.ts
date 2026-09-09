import assert from "node:assert/strict";
import test from "node:test";
import { filterSelectOptions } from "./select-options.ts";

const options = [
  { value: "malaria", label: "Malaria" },
  { value: "type_1_diabetes", label: "Type 1 Diabetes" },
  { value: "type_2_diabetes", label: "Type 2 Diabetes" },
];

test("option filtering ignores case and surrounding whitespace without changing values or order", () => {
  assert.deepEqual(filterSelectOptions(options, "  DIABETES "), options.slice(1));
  assert.equal(filterSelectOptions(options, "type 2")[0], options[2]);
  assert.deepEqual(filterSelectOptions(options, ""), options);
  assert.deepEqual(filterSelectOptions(options, "not an option"), []);
  assert.equal(options.length, 3);
});
