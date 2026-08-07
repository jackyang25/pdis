/**
 * Every tool is checked the same way at the import boundary.
 *
 * Before this, Scout ran four deep contract checks while Inspector and Aligner ran a
 * single `if`, and all of it lived inside the module that owns the envelope. The
 * asymmetry was invisible because nothing compared the three.
 */

import assert from "node:assert/strict";
import test from "node:test";

import { RESULT_CONTRACTS, type ResultType } from "./result-contracts.ts";

const TOOLS: ResultType[] = ["aligner", "inspector", "scout"];

test("every tool has exactly one contract, and no tool is missing one", () => {
  assert.deepEqual(Object.keys(RESULT_CONTRACTS).sort(), [...TOOLS].sort());
});

test("each contract refuses an empty analysis and names the tool", () => {
  // The same call shape for all three: hand it a result, get a reason or nothing.
  for (const tool of TOOLS) {
    assert.throws(
      () => RESULT_CONTRACTS[tool]({}),
      (error: Error) => error.message.includes(tool),
      `${tool} did not name itself in its refusal`,
    );
  }
});

test("Inspector refuses an assessment missing a derived value", () => {
  // `status`, `level`, and `status_counts` arrived with the rubric ledger, so a file
  // written before it has the right field names and none of these. Without the
  // check, every unit would render blank rather than being refused.
  const withUnits = (unit: Record<string, unknown>) => ({
    inspection: {
      sections: [
        {
          section_name: "Profile",
          status_counts: { met: 0, could_be_stronger: 0, not_met: 1, not_applicable: 0 },
          units: [unit],
        },
      ],
      document_findings: [],
    },
  });

  const complete = {
    variable_name: "Efficacy",
    status: "not_met",
    findings: [
      { reason: "missing", statement: "Not stated.", level: "not_met" },
    ],
  };
  RESULT_CONTRACTS.inspector(withUnits(complete));

  const { status, ...noStatus } = complete;
  assert.throws(() => RESULT_CONTRACTS.inspector(withUnits(noStatus)), /unit status/);

  const noLevel = { ...complete, findings: [{ reason: "missing", statement: "x" }] };
  assert.throws(() => RESULT_CONTRACTS.inspector(withUnits(noLevel)), /finding level/);
});

test("Inspector refuses a section with no units", () => {
  assert.throws(
    () =>
      RESULT_CONTRACTS.inspector({
        inspection: {
          sections: [{ section_name: "Profile", status_counts: {} }],
          document_findings: [],
        },
      }),
    /units/,
  );
});

test("Aligner refuses a result that cannot form a comparison", () => {
  const alignment = {
    documents: [{ doc_id: "a" }, { doc_id: "b" }, { doc_id: "c" }],
    edges: [
      { reference_doc_id: "a", comparison_doc_id: "b", question: "?" },
      { reference_doc_id: "b", comparison_doc_id: "c", question: "?" },
    ],
  };
  RESULT_CONTRACTS.aligner({ alignment });

  assert.throws(
    () => RESULT_CONTRACTS.aligner({ alignment: { ...alignment, documents: [{ doc_id: "a" }] } }),
    /fewer than two documents/,
  );
  assert.throws(
    () => RESULT_CONTRACTS.aligner({ alignment: { ...alignment, edges: [] } }),
    /no comparison/,
  );
  // A comparison pointing at a document the file does not carry would render as a
  // blank side rather than as the error it is.
  assert.throws(
    () =>
      RESULT_CONTRACTS.aligner({
        alignment: {
          ...alignment,
          edges: [{ reference_doc_id: "a", comparison_doc_id: "absent", question: "?" }],
        },
      }),
    /does not carry/,
  );
});

test("a contract reports a reason a reader can act on", () => {
  // "cannot be read" plus what is missing, rather than a bare boolean, because the
  // version gate already covers "wrong vintage" and this covers "wrong shape".
  assert.throws(
    () => RESULT_CONTRACTS.inspector({}),
    /this inspector result cannot be read: it carries no assessment/,
  );
});
