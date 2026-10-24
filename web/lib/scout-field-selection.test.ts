import assert from "node:assert/strict";
import test from "node:test";

import type { ScoutResponse, Variable } from "./api.ts";
import { continueScout } from "./api.ts";
import { targetReviewFixture } from "../test-support/scout-review-fixture.ts";
import {
  fieldSelectionSummary,
  searchableFields,
  withEveryFieldSearched,
  withFieldSearched,
} from "./scout-field-selection.ts";

function field(name: string, stated = true): Variable {
  const quote = stated ? `${name} target.` : "";
  return {
    name, description: "", block_ids: stated ? [`doc/${name}`] : [], document_target: quote,
    document_spans: stated ? [{ quote, block_ids: [`doc/${name}`] }] : [],
    definition_mode: "fixed", target_resolved: true, target_resolution_reason: "Resolved.",
    evidence_domain: "clinical", supplies_scope: "", entities: [], quantitative_target_ids: [],
    quantitative_statement_dispositions: [], quantitative_target_status: "not_applicable",
    quantitative_target_status_reason: "",
  };
}

function draft(not_searched_fields: string[] = []): Pick<ScoutResponse, "variables" | "not_searched_fields"> {
  return {
    variables: [field("efficacy"), field("cogs", false), field("safety"), field("storage")],
    not_searched_fields,
  };
}

test("only fields that state a target can be searched", () => {
  assert.deepEqual(searchableFields(draft()).map((item) => item.name), ["efficacy", "safety", "storage"]);
});

test("every field is searched until the reviewer leaves one out", () => {
  const summary = fieldSelectionSummary(draft());
  assert.equal(summary.searched, 3);
  assert.equal(summary.total, 3);
  assert.equal(summary.blocked, "");
  assert.equal(summary.sentence, "All 3 fields will be searched.");
});

test("the selection is stored as exclusions, in document order whatever the click order", () => {
  const first = withFieldSearched(draft(), "storage", false);
  const second = withFieldSearched(draft(first), "efficacy", false);
  assert.deepEqual(second, ["efficacy", "storage"]);
  assert.deepEqual(withFieldSearched(draft(second), "storage", true), ["efficacy"]);
  assert.equal(fieldSelectionSummary(draft(second)).sentence, "1 of 3 fields will be searched.");
});

test("a field that states no target cannot be left out, because it was never searchable", () => {
  assert.deepEqual(withFieldSearched(draft(), "cogs", false), []);
});

test("none and all are one click each, and none blocks the continuation with a reason", () => {
  const none = withEveryFieldSearched(draft(), false);
  assert.deepEqual(none, ["efficacy", "safety", "storage"]);
  const summary = fieldSelectionSummary(draft(none));
  assert.equal(summary.searched, 0);
  assert.equal(summary.blocked, "Select at least one field to search.");
  assert.deepEqual(withEveryFieldSearched(draft(none), true), []);
});

test("the continuation sends the reviewer's selection with the rest of the draft", async (t) => {
  const reviewed = { ...targetReviewFixture("completed") };
  reviewed.not_searched_fields = withFieldSearched(
    reviewed, searchableFields(reviewed)[0].name, false,
  );
  assert.equal(reviewed.not_searched_fields.length, 1);
  let sent: { draft: ScoutResponse } | undefined;
  t.mock.method(globalThis, "fetch", async (_url: string, init: RequestInit) => {
    sent = JSON.parse(String(init.body));
    return new Response(`${JSON.stringify({ event: "complete", result: { ...reviewed, phase: "final" } })}\n`);
  });
  await continueScout(reviewed);
  assert.deepEqual(sent?.draft.not_searched_fields, reviewed.not_searched_fields);
});
