/**
 * The trace places citations the result already carries, and nothing else.
 *
 * The pressure this resists is making the viewer look complete. An unanswered
 * question has no passage; anchoring it at a "probable" block would invent
 * provenance out of an expectation about where an answer ought to live, which no source
 * states. These tests are what keeps that from creeping back.
 */

import assert from "node:assert/strict";
import test from "node:test";

import type { ContentBlock, GateReview, QuestionAssessment } from "./api.ts";
import {
  buildScreenerDocumentAnnotations,
} from "./screener-document-trace.ts";

function block(id: string, docId: string): ContentBlock {
  return {
    id,
    doc_id: docId,
    ordinal: 1,
    block_type: "paragraph",
    content: "text",
    heading_stack: [],
    section_label: null,
    structural_meta: {},
    style_hint: {},
  };
}

function question(
  id: string,
  state: QuestionAssessment["state"],
  overrides: Partial<QuestionAssessment> = {},
): QuestionAssessment {
  return {
    id,
    text: `Question ${id}?`,
    state,
    requirement: "required",
    statement: "",
    missing: "",
    source: null,
    cited_block_ids: [],
    context_label: "",
    ...overrides,
  };
}

function review(
  questions: QuestionAssessment[],
  overrides: Partial<GateReview> = {},
): GateReview {
  return {
    gate_id: "ep2",
    gate_label: "End of Phase 2",
    bank_source: "Stage Gate Questions - All Gates.docx, test fixture",
    documents: [{ doc_id: "profile", source_type: "itpp" }],
    disciplines: [{ id: "cmc", label: "CMC", questions }],
    context_labels: [],
    org: "bmgf",
    intervention_class: "vaccine",
    indication: "malaria",
    blocks: [block("profile:1", "profile")],
    ...overrides,
  };
}

const cited = (id: string, blockIds: string[]) =>
  question(id, "answered", {
    source: "document",
    cited_block_ids: blockIds,
    statement: "The profile states it.",
  });

const partly = (id: string, blockIds: string[]) =>
  question(id, "partly_answered", {
    source: "document",
    cited_block_ids: blockIds,
    statement: "The profile states the target.",
    missing: "Zone IVb stability data.",
  });

test("a partial is placed too, and carries what it leaves open", () => {
  // The passages a document got part of the way with are the most useful thing in the
  // trace, because that is where a specific ask to the grantee comes from.
  const [annotation] = buildScreenerDocumentAnnotations(
    review([partly("A", ["profile:1"])]),
  );
  assert.equal(annotation.kind, "partly_answered");
  assert.equal(annotation.layerLabel, "Partly answered");
  assert.equal(annotation.emphasis?.tone, "warning");
  assert.equal(annotation.sourceRef.missing, "Zone IVb stability data.");
});

test("a whole answer is success and a partial is warning, in the shared tones", () => {
  // Not grey: a passage that answered a question in grey reads as one nobody looked at.
  // And the same tone every other tool uses for "the thing asked for is there", so a
  // reader carries the colours between tools rather than relearning them.
  const [answered] = buildScreenerDocumentAnnotations(
    review([cited("A", ["profile:1"])]),
  );
  assert.equal(answered.emphasis?.tone, "success");
  assert.equal(answered.sourceRef.missing, "");

  const [partial] = buildScreenerDocumentAnnotations(
    review([partly("B", ["profile:1"])]),
  );
  assert.equal(partial.emphasis?.tone, "warning");
});

test("only answers read from a document are placed", () => {
  const annotations = buildScreenerDocumentAnnotations(
    review([
      cited("A", ["profile:1"]),
      question("B", "not_found", { statement: "Not stated." }),
      question("C", "not_applicable"),
      question("D", "answered", { source: "context", context_label: "CMC Report" }),
      // A partial from pasted context has no passage either.
      question("E", "partly_answered", {
        source: "context",
        context_label: "CMC Report",
        missing: "The rest.",
      }),
    ]),
  );
  assert.deepEqual(
    annotations.map((annotation) => annotation.id),
    ["A"],
  );
});

test("an unanswered question is never anchored to a probable block", () => {
  // The hint names a document. If it ever became a display anchor, the viewer would
  // show a guess as provenance.
  const annotations = buildScreenerDocumentAnnotations(
    review([question("A", "not_found", { })]),
  );
  assert.deepEqual(annotations, []);
});

test("an answer with an empty citation list is not placed", () => {
  // The service contract refuses this, so it should be unreachable — but the trace
  // must not produce a marker with nothing behind it if it ever arrives.
  const annotations = buildScreenerDocumentAnnotations(
    review([question("A", "answered", { source: "document", cited_block_ids: [] })]),
  );
  assert.deepEqual(annotations, []);
});

test("annotations claim whole blocks and never invent a span", () => {
  // Screener records block lineage, not quotations. A synthesised span would be a
  // provenance claim the model never made.
  const [annotation] = buildScreenerDocumentAnnotations(
    review([cited("A", ["profile:1"])]),
  );
  assert.deepEqual(annotation.spans, []);
  assert.deepEqual(annotation.blockIds, ["profile:1"]);
  assert.equal(annotation.displayAnchorBlockId, undefined);
});

test("annotations keep bank order across disciplines", () => {
  const annotations = buildScreenerDocumentAnnotations(
    review([], {
      disciplines: [
        { id: "cmc", label: "CMC", questions: [cited("C1", ["profile:1"])] },
        {
          id: "cd",
          label: "CD",
          questions: [cited("D1", ["profile:1"]), cited("D2", ["profile:1"])],
        },
      ],
    }),
  );
  assert.deepEqual(
    annotations.map((annotation) => annotation.id),
    ["C1", "D1", "D2"],
  );
});

test("a question the gate requires is labelled as one", () => {
  const [annotation] = buildScreenerDocumentAnnotations(
    review([cited("A", ["profile:1"])]),
  );
  assert.equal(annotation.statusLabel, "Required at this gate");
  assert.equal(annotation.sourceRef.requirement, "required");
});
