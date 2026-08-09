/**
 * Every tool is checked the same way at the import boundary.
 *
 * Before this, Scout ran four deep contract checks while Inspector and Aligner ran a
 * single `if`, and all of it lived inside the module that owns the envelope. The
 * asymmetry was invisible because nothing compared them.
 */

import assert from "node:assert/strict";
import test from "node:test";

import { RESULT_CONTRACTS, type ResultType } from "./result-contracts.ts";

const TOOLS: ResultType[] = ["aligner", "expert", "inspector", "scout"];

test("every tool has exactly one contract, and no tool is missing one", () => {
  assert.deepEqual(Object.keys(RESULT_CONTRACTS).sort(), [...TOOLS].sort());
});

test("each contract refuses an empty analysis and names the tool", () => {
  // One call shape for every tool: hand it a result, get a reason or nothing.
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
      { edge_id: "a-to-b", reference_doc_id: "a", comparison_doc_id: "b", question: "?" },
      { edge_id: "b-to-c", reference_doc_id: "b", comparison_doc_id: "c", question: "?" },
    ],
    findings: [
      {
        requirement_id: "a-to-b/r-001",
        edge_id: "a-to-b",
        requirement: "Annual dosing.",
        reference_block_ids: ["a:1"],
        verdict: "meets",
        statement: "It states annual dosing.",
        gap: "",
        comparison_block_ids: ["b:1"],
      },
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
          edges: [
            {
              edge_id: "a-to-absent",
              reference_doc_id: "a",
              comparison_doc_id: "absent",
              question: "?",
            },
          ],
        },
      }),
    /does not carry/,
  );
});

test("Aligner refuses a result whose findings cannot be placed or read", () => {
  // A run that compared nothing looks exactly like one that found nothing wrong, and
  // an unknown verdict has no label, no colour, and no meaning to a reader.
  const alignment = {
    documents: [{ doc_id: "a" }, { doc_id: "b" }],
    edges: [
      { edge_id: "a-to-b", reference_doc_id: "a", comparison_doc_id: "b", question: "?" },
    ],
    findings: [
      {
        requirement_id: "a-to-b/r-001",
        edge_id: "a-to-b",
        requirement: "Annual dosing.",
        reference_block_ids: ["a:1"],
        verdict: "meets",
        statement: "It states annual dosing.",
        gap: "",
        comparison_block_ids: ["b:1"],
      },
    ],
  };
  RESULT_CONTRACTS.aligner({ alignment });

  assert.throws(
    () => RESULT_CONTRACTS.aligner({ alignment: { ...alignment, findings: [] } }),
    /no findings/,
  );
  assert.throws(
    () =>
      RESULT_CONTRACTS.aligner({
        alignment: {
          ...alignment,
          findings: [{ ...alignment.findings[0], edge_id: "b-to-a" }],
        },
      }),
    /a comparison the file does not carry/,
  );
  assert.throws(
    () =>
      RESULT_CONTRACTS.aligner({
        alignment: {
          ...alignment,
          // The vocabulary this replaced. A saved file using it must not render.
          findings: [{ ...alignment.findings[0], verdict: "modified" }],
        },
      }),
    /unknown verdict/,
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
