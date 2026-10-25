import assert from "node:assert/strict";
import test from "node:test";

import type { DraftResult, DraftVariable } from "./api.ts";
import { RESULT_CONTRACTS } from "./result-contracts.ts";
import { packDrafterResult, runLabel, runScope, unpackDrafterResult } from "./result-file.ts";

/** The held run a file is written for; packing never mints identity of its own. */
const RUN = { id: "run-1", created_at: "2026-01-01T00:00:00.000Z" };

function suggested(name: string, overrides: Partial<DraftVariable> = {}): DraftVariable {
  return {
    name, label: name.split(".")[1], description: "", evidence_domain: "clinical",
    status: "complete", failure: null,
    observations: [{
      id: `${name}:o1`, basis: "comparable_product", url: "https://example.org", title: "Trial A",
      source_label: "PubMed", product: "RTS,S", measure: "efficacy", quote: "56%",
      value: { value: 56, lower: null, upper: null, unit: "%", text: "stated" }, numeric_eligible: true,
      published_at: "2021-04-01", published_precision: "month",
    }],
    statistics: [],
    suggestion: {
      kind: "range", minimum: "50%", preferred: "75%", statement: "", rationale: "Comparable products reached 56%.",
      leans_on: "comparable_products", basis_ids: [`${name}:o1`],
    },
    unread_findings: 0,
    unverified_quotes: 0,
    ...overrides,
  };
}

function draft(...variables: DraftVariable[]): DraftResult {
  return {
    org: "bmgf", source_type: "itpp", intervention_class: "vaccine", indication: "malaria",
    display_name: "BMGF Intervention TPP - Vaccine", sources: ["pubmed"], failed_sources: [],
    unconfigured_sources: [], source_errors: [],
    variables: variables.length ? variables : [suggested("vaccine.efficacy"), suggested("vaccine.safety")],
  };
}

test("the saved-file contract refuses a suggestion with a basis it does not hold", () => {
  assert.throws(() => RESULT_CONTRACTS.drafter({}), /drafter/);
  const foreign = suggested("vaccine.efficacy");
  foreign.suggestion = { ...foreign.suggestion!, basis_ids: ["vaccine.efficacy:o9"] };
  assert.throws(() => RESULT_CONTRACTS.drafter(draft(foreign)), /basis/);
});

test("the saved-file contract holds kinds, bases and failures to the server's rules", () => {
  const unknownFailure = suggested("vaccine.efficacy", { status: "failed", suggestion: null,
    failure: { code: "something_else" as never, message: "x", cause: null } });
  assert.throws(() => RESULT_CONTRACTS.drafter(draft(unknownFailure)), /failure/);
  const mismatched = suggested("vaccine.efficacy");
  mismatched.suggestion = { ...mismatched.suggestion!, leans_on: "guidance" };
  assert.throws(() => RESULT_CONTRACTS.drafter(draft(mismatched)), /leans on/);
  const noBasis = suggested("vaccine.efficacy");
  noBasis.suggestion = { ...noBasis.suggestion!, basis_ids: [] };
  assert.throws(() => RESULT_CONTRACTS.drafter(draft(noBasis)), /basis/);
});

test("the saved-file contract refuses a date without its precision, or a precision without a date", () => {
  for (const [published_at, published_precision] of [["2021-04-01", ""], [null, "year"]] as const) {
    const variable = suggested("vaccine.efficacy");
    variable.observations = [{ ...variable.observations[0], published_at, published_precision }];
    assert.throws(() => RESULT_CONTRACTS.drafter(draft(variable)), /publication date/);
  }
  const undated = suggested("vaccine.efficacy");
  undated.observations = [{ ...undated.observations[0], published_at: null, published_precision: "" }];
  assert.doesNotThrow(() => RESULT_CONTRACTS.drafter(draft(undated)));
});

test("a draft round-trips through a result file as soon as the run finishes", () => {
  const result = draft();
  const file = packDrafterResult(result, RUN);
  assert.equal(file.result_type, "drafter");
  // Drafter reads no document, so nothing travels beside the analysis.
  assert.deepEqual(file.source_documents, []);
  assert.deepEqual(unpackDrafterResult(JSON.parse(JSON.stringify(file))), result);
  assert.equal(runLabel(result, "drafter"), "Malaria");
  assert.equal(runScope(result, "drafter"), "Vaccine · iTPP");
});

test("a failed call says why by code, and a variable left without evidence names no call", () => {
  // `cause` is the machine-readable half of a failure. Only the two failures a model or
  // provider call raises carry one; `evidence_unavailable` is concluded from counts.
  const failed = (code: NonNullable<DraftVariable["failure"]>["code"], cause: NonNullable<DraftVariable["failure"]>["cause"]) =>
    suggested("vaccine.efficacy", { status: "failed", suggestion: null, failure: { code, message: "It failed.", cause } });
  RESULT_CONTRACTS.drafter(draft(failed("suggestion_failed", "response_truncated")));
  RESULT_CONTRACTS.drafter(draft(failed("evidence_unavailable", null)));
  assert.throws(() => RESULT_CONTRACTS.drafter(draft(failed("search_planning_failed", null))), /known cause/);
  assert.throws(() => RESULT_CONTRACTS.drafter(draft(failed("evidence_unavailable", "provider_error"))), /no call's cause/);
});

test("the counts of what a reading set aside are counts", () => {
  RESULT_CONTRACTS.drafter(draft(suggested("vaccine.efficacy", { unverified_quotes: 2 })));
  assert.throws(() => RESULT_CONTRACTS.drafter(draft(suggested("vaccine.efficacy", { unverified_quotes: -1 }))), /unverified_quotes is a count/);
  assert.throws(() => RESULT_CONTRACTS.drafter(draft(suggested("vaccine.efficacy", { unread_findings: 1.5 }))), /unread_findings is a count/);
});

test("a draft saved before its sources carried their dates is re-run, not read", () => {
  const file = packDrafterResult(draft(), RUN);
  assert.equal(file.analysis_version, 4);
  assert.throws(() => unpackDrafterResult({ ...file, analysis_version: 3 }), /re-run the drafter analysis/);
});

test("a saved number names the words that state it, and a figure the observations it came from", () => {
  const saved = draft();
  const variable = saved.variables[0];
  const broken = structuredClone(saved);
  broken.variables[0].observations = variable.observations.map((observation) =>
    observation.value ? { ...observation, value: { ...observation.value, text: " " } } : observation);
  assert.throws(() => packDrafterResult(broken, RUN), /name the words that state it/);
  const orphan = structuredClone(saved);
  orphan.variables[0].statistics = [{ unit: "%", observation_ids: ["missing", "also-missing"], count: 2,
    minimum: 1, maximum: 2, median: 1.5, lower_quartile: 1, upper_quartile: 2 }];
  assert.throws(() => packDrafterResult(orphan, RUN), /observations it was computed from/);
});
