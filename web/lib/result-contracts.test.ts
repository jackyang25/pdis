/**
 * Every tool is checked the same way at the import boundary.
 *
 * Before this, Scout ran four deep contract checks while Inspector and Aligner ran a
 * single `if`, and all of it lived inside the module that owns the envelope. The
 * asymmetry was invisible because nothing compared them.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";

import { RESULT_CONTRACTS, type ResultType } from "./result-contracts.ts";

const TOOLS: ResultType[] = ["aligner", "screener", "inspector", "scout", "drafter"];

function inspectorSections(sections: unknown[]) {
  return { inspection: { blocks: [], document_findings: [], applicability_facts: {}, consistency_status: "complete", consistency_failure_code: null,
    rubric_resolutions: [{ rubric_id: "test", display_name: "Test", status: "included", reason_code: "test", reason: "Test" }],
    reviews: [{ rubric: { id: "test", revision: null, display_name: "Test", authority: "Test", scope: "Test",
      evidence_scope: "mapped_section", stage_guidance: "", mirrors: null, sources: [], requirements: [] }, assessment_status: "complete", sections }] } };
}

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
  // `verdict_counts` is computed during serialization, so a file written before it has
  // the right field names and not this one. Without the check every section header
  // would render blank rather than the file being refused.
  const withUnits = (unit: Record<string, unknown>) => inspectorSections([
        {
          section_name: "Profile",
          verdict_counts: { specified: 0, not_present: 1 },
          units: [unit],
        },
      ]);

  const complete = { id: "unit", cited_block_ids: [], variable_name: "Efficacy", verdict: "not_present", statement: "Not stated." };
  RESULT_CONTRACTS.inspector(withUnits(complete));

  const { verdict, ...noVerdict } = complete;
  assert.throws(() => RESULT_CONTRACTS.inspector(withUnits(noVerdict)), /unit verdict/);

  assert.throws(
    () =>
      RESULT_CONTRACTS.inspector(inspectorSections([{ section_name: "Profile", units: [complete] }])),
    /verdict counts/,
  );
});

test("Inspector accepts a sound unit, which states nothing", () => {
  // The regression this exists for. The contract used to walk `units[].findings[]` and
  // require a `reason`, a `level` and a unit `status` on the way down - a shape check
  // rather than a check of what the interface needs. When those three fields went, every
  // freshly built result stopped hydrating and the page threw a client-side exception.
  //
  // A `specified` unit carries an empty statement, which is the common case, so the
  // contract must not require text there either.
  RESULT_CONTRACTS.inspector(inspectorSections([
        {
          section_name: "Profile",
          verdict_counts: { specified: 1 },
          units: [{ id: "unit", cited_block_ids: [], variable_name: "Efficacy", verdict: "specified", statement: "" }],
        },
      ]));
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
        reference_visual_block_ids: [],
        comparison_visual_block_ids: [],
        reference_spans: [{ quote: "cited", block_ids: ["a:1"] }],
        verdict: "meets",
        statement: "It states annual dosing.",
        gap: "",
        comparison_spans: [{ quote: "cited", block_ids: ["b:1"] }],
      },
      {
        requirement_id: "b-to-c/r-001",
        edge_id: "b-to-c",
        requirement: "Six-monthly dosing.",
        reference_visual_block_ids: [],
        comparison_visual_block_ids: [],
        reference_spans: [{ quote: "cited", block_ids: ["b:1"] }],
        verdict: "meets",
        statement: "It states six-monthly dosing.",
        gap: "",
        comparison_spans: [{ quote: "cited", block_ids: ["c:1"] }],
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
        reference_visual_block_ids: [],
        comparison_visual_block_ids: [],
        reference_spans: [{ quote: "cited", block_ids: ["a:1"] }],
        verdict: "meets",
        statement: "It states annual dosing.",
        gap: "",
        comparison_spans: [{ quote: "cited", block_ids: ["b:1"] }],
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

test("Inspector's contract only requires fields the service publishes", () => {
  // The bug this exists for: the contract required `status`, `level` and
  // `status_counts` long after the service stopped emitting them, so every freshly
  // built result was refused and the page threw a client-side exception. Hand-written
  // fixtures could not catch it, because they were written to match the contract.
  //
  // Reading the service's own schema closes that loop: a field the contract insists on
  // has to be one `api/schemas.py` declares, or the contract is checking for something
  // no result will ever carry.
  const schema = readFileSync(
    path.resolve(import.meta.dirname, "..", "..", "api", "schemas.py"),
    "utf8",
  );
  const declared = (model: string) => {
    const block = schema.slice(schema.indexOf(`class ${model}(BaseModel):`));
    return new Set(
      [...block.slice(0, block.indexOf("\n\nclass ")).matchAll(/^\s{4}(\w+):/gm)].map(
        (match) => match[1],
      ),
    );
  };

  const contract = readFileSync(
    path.resolve(import.meta.dirname, "result-contracts.ts"),
    "utf8",
  );
  const body = contract.slice(
    contract.indexOf("function assertInspectorReadable"),
    contract.indexOf("// --- Aligner"),
  );

  const section = declared("SectionAssessmentOut");
  const unit = declared("AssessmentOut");
  assert.ok(section.size > 0 && unit.size > 0, "the API schema could not be read");

  // Every property the contract names on a section or a unit, however it reaches it.
  const named = [...body.matchAll(/(?:entry|held|unit as Record<string, unknown>)\)?\.(\w+)/g)]
    .map((match) => match[1])
    .filter((name) => name !== "then");
  assert.ok(named.length > 0, "the contract names no fields, so this checks nothing");
  for (const field of named) {
    assert.ok(
      section.has(field) || unit.has(field),
      `the contract requires ${field}, which the service does not publish`,
    );
  }
});

test("Aligner refuses a comparison with no findings, or findings out of sequence", () => {
  // The service mints requirement IDs positionally per comparison, so each comparison's
  // findings run r-001, r-002, ... A gap is a requirement that went missing; a comparison
  // with none is a read that failed, because a reference document states at least one.
  const finding = (edge: string, index: number) => ({
    requirement_id: `${edge}/r-${String(index).padStart(3, "0")}`,
    edge_id: edge,
    requirement: "Annual dosing.",
    reference_visual_block_ids: [],
    comparison_visual_block_ids: [],
    reference_spans: [{ quote: "cited", block_ids: ["a:1"] }],
    verdict: "meets",
    statement: "It states annual dosing.",
    gap: "",
    comparison_spans: [{ quote: "cited", block_ids: ["b:1"] }],
  });
  const alignment = {
    documents: [{ doc_id: "a" }, { doc_id: "b" }, { doc_id: "c" }],
    edges: [
      { edge_id: "a-to-b", reference_doc_id: "a", comparison_doc_id: "b", question: "?" },
      { edge_id: "b-to-c", reference_doc_id: "b", comparison_doc_id: "c", question: "?" },
    ],
    findings: [finding("a-to-b", 1), finding("a-to-b", 2), finding("b-to-c", 1)],
  };
  RESULT_CONTRACTS.aligner({ alignment });
  assert.throws(
    () => RESULT_CONTRACTS.aligner({ alignment: { ...alignment, findings: alignment.findings.slice(0, 2) } }),
    /b-to-c carries no findings/,
  );
  assert.throws(
    () => RESULT_CONTRACTS.aligner({ alignment: { ...alignment, findings: [finding("a-to-b", 2), finding("b-to-c", 1)] } }),
    /out of sequence/,
  );
});

test("Screener requires every model decision to say what the material holds", () => {
  // `not_found` included: it is an observation of the supplied material, not a blank. Only
  // the one state no model reached, `not_applicable`, says nothing.
  const review = (question: Record<string, unknown>) => ({ review: {
    gate_id: "eop1", gate_label: "EOP1", documents: [{ doc_id: "doc" }],
    blocks: [{ id: "doc:1", doc_id: "doc" }],
    disciplines: [{ label: "CMC", questions: [{ id: "q1", text: "Is the route set?", cited_block_ids: [], ...question }] }],
  } });
  RESULT_CONTRACTS.screener(review({ state: "not_found", statement: "The plan names no route." }));
  RESULT_CONTRACTS.screener(review({ state: "not_applicable", statement: "" }));
  assert.throws(() => RESULT_CONTRACTS.screener(review({ state: "not_found", statement: " " })), /statement/);
  assert.throws(() => RESULT_CONTRACTS.screener(review({ state: "not_applicable", statement: "Read anyway." })), /no model read/);
});
