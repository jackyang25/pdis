import assert from "node:assert/strict";
import test from "node:test";

import type { DraftResult, DraftVariable } from "./api.ts";
import { RESULT_CONTRACTS } from "./result-contracts.ts";
import { packDrafterResult, runLabel, runScope, unpackDrafterResult } from "./result-file.ts";

function suggested(name: string, overrides: Partial<DraftVariable> = {}): DraftVariable {
  return {
    name, label: name.split(".")[1], description: "", evidence_domain: "clinical",
    status: "complete", failure: null,
    observations: [{
      id: `${name}:o1`, basis: "comparable_product", url: "https://example.org", title: "Trial A",
      source_label: "PubMed", product: "RTS,S", measure: "efficacy", quote: "56%",
      value: { value: 56, lower: null, upper: null, unit: "%" }, numeric_eligible: true,
    }],
    statistics: [],
    suggestion: {
      kind: "range", minimum: "50%", preferred: "75%", statement: "", rationale: "Comparable products reached 56%.",
      leans_on: "comparable_products", basis_ids: [`${name}:o1`],
    },
    unread_findings: 0,
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
    failure: { code: "something_else" as never, message: "x" } });
  assert.throws(() => RESULT_CONTRACTS.drafter(draft(unknownFailure)), /failure/);
  const mismatched = suggested("vaccine.efficacy");
  mismatched.suggestion = { ...mismatched.suggestion!, leans_on: "guidance" };
  assert.throws(() => RESULT_CONTRACTS.drafter(draft(mismatched)), /leans on/);
  const noBasis = suggested("vaccine.efficacy");
  noBasis.suggestion = { ...noBasis.suggestion!, basis_ids: [] };
  assert.throws(() => RESULT_CONTRACTS.drafter(draft(noBasis)), /basis/);
});

test("a draft round-trips through a result file as soon as the run finishes", () => {
  const result = draft();
  const file = packDrafterResult(result);
  assert.equal(file.result_type, "drafter");
  // Drafter reads no document, so nothing travels beside the analysis.
  assert.deepEqual(file.source_documents, []);
  assert.deepEqual(unpackDrafterResult(JSON.parse(JSON.stringify(file))), result);
  assert.equal(runLabel(result, "drafter"), "Malaria");
  assert.equal(runScope(result, "drafter"), "Vaccine · iTPP");
});
