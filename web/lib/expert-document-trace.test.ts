/**
 * The trace places citations the result already carries, and nothing else.
 *
 * The pressure this resists is making the viewer look complete. An unanswered
 * question has no passage; anchoring it at a "probable" block would invent
 * provenance out of the `likely_in` hint, which is exactly the guess that no longer
 * decides anything. These tests are what keeps that from creeping back.
 */

import assert from "node:assert/strict";
import test from "node:test";

import type { ContentBlock, GateReview, QuestionAssessment } from "./api.ts";
import {
  answersPerDocument,
  buildExpertDocumentAnnotations,
} from "./expert-document-trace.ts";

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
    pq: false,
    likely_in: [],
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
    gate_id: "eop2",
    gate_label: "End of Phase 2",
    bank_source: "Stage Gate Question Bank — SME Edition v5, test fixture",
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
  const [annotation] = buildExpertDocumentAnnotations(
    review([partly("A", ["profile:1"])]),
  );
  assert.equal(annotation.kind, "partly_answered");
  assert.equal(annotation.layerLabel, "Partly answered");
  assert.equal(annotation.emphasis?.tone, "caution");
  assert.equal(annotation.sourceRef.missing, "Zone IVb stability data.");
});

test("a whole answer is neutral, so one colour never means two things", () => {
  const [annotation] = buildExpertDocumentAnnotations(
    review([cited("A", ["profile:1"])]),
  );
  assert.equal(annotation.emphasis?.tone, "neutral");
  assert.equal(annotation.sourceRef.missing, "");
});

test("only answers read from a document are placed", () => {
  const annotations = buildExpertDocumentAnnotations(
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
  const annotations = buildExpertDocumentAnnotations(
    review([question("A", "not_found", { likely_in: ["itpp"] })]),
  );
  assert.deepEqual(annotations, []);
});

test("an answer with an empty citation list is not placed", () => {
  // The service contract refuses this, so it should be unreachable — but the trace
  // must not produce a marker with nothing behind it if it ever arrives.
  const annotations = buildExpertDocumentAnnotations(
    review([question("A", "answered", { source: "document", cited_block_ids: [] })]),
  );
  assert.deepEqual(annotations, []);
});

test("annotations claim whole blocks and never invent a span", () => {
  // Expert records block lineage, not quotations. A synthesised span would be a
  // provenance claim the model never made.
  const [annotation] = buildExpertDocumentAnnotations(
    review([cited("A", ["profile:1"])]),
  );
  assert.deepEqual(annotation.spans, []);
  assert.deepEqual(annotation.blockIds, ["profile:1"]);
  assert.equal(annotation.displayAnchorBlockId, undefined);
});

test("annotations keep bank order across disciplines", () => {
  const annotations = buildExpertDocumentAnnotations(
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

test("a prequalification question is labelled as one", () => {
  const [annotation] = buildExpertDocumentAnnotations(
    review([{ ...cited("A", ["profile:1"]), pq: true }]),
  );
  assert.equal(annotation.statusLabel, "WHO prequalification");
  assert.equal(annotation.sourceRef.pq, true);
});

test("the per-document counts come from the same annotations the trace renders", () => {
  const counts = answersPerDocument(
    review([], {
      documents: [
        { doc_id: "profile", source_type: "itpp" },
        { doc_id: "plan", source_type: "ipdp" },
      ],
      blocks: [block("profile:1", "profile"), block("plan:1", "plan")],
      disciplines: [
        {
          id: "cmc",
          label: "CMC",
          questions: [
            cited("A", ["profile:1"]),
            // Cites both, so it counts once for each: the question asked here is what
            // a document answered, not how many questions exist.
            cited("B", ["profile:1", "plan:1"]),
            question("C", "not_found"),
          ],
        },
      ],
    }),
  );
  assert.deepEqual(counts, [
    { docId: "profile", sourceType: "itpp", count: 2 },
    { docId: "plan", sourceType: "ipdp", count: 1 },
  ]);
});

test("a document that answered nothing is still listed, at zero", () => {
  // Omitting it would read as "not uploaded", which is a different fact.
  const counts = answersPerDocument(
    review([question("A", "not_found")], {
      documents: [
        { doc_id: "profile", source_type: "itpp" },
        { doc_id: "plan", source_type: "ipdp" },
      ],
    }),
  );
  assert.deepEqual(
    counts.map((entry) => [entry.sourceType, entry.count]),
    [["itpp", 0], ["ipdp", 0]],
  );
});
