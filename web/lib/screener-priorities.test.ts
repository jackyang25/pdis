/**
 * What Screener counts, and the numbers a reader is asked to trust.
 *
 * The counts are derived rather than carried, so this is where "the figures sum to
 * the total" is actually guaranteed. If it stops holding, the header row silently
 * stops adding up and nothing else notices.
 */

import assert from "node:assert/strict";
import test from "node:test";

import type { GateReview, QuestionAssessment } from "./api.ts";
import {
  countStates,
  groupedByDiscipline,
  countRequiredInState,
  questionsInState,
} from "./screener-priorities.ts";

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
  disciplines: { id: string; label: string; questions: QuestionAssessment[] }[],
  overrides: Partial<GateReview> = {},
): GateReview {
  return {
    gate_id: "ep1",
    gate_label: "End of Phase 1",
    bank_source: "Stage Gate Questions - All Gates.docx, test fixture",
    documents: [{ doc_id: "profile", source_type: "itpp" }],
    disciplines,
    context_labels: [],
    org: "bmgf",
    intervention_class: "vaccine",
    indication: "malaria",
    blocks: [],
    ...overrides,
  };
}

test("the counts sum to the total, so the header row checks itself", () => {
  const counts = countStates(
    review([
      {
        id: "cd",
        label: "Clinical Development",
        questions: [
          question("A", "answered", { source: "document", cited_block_ids: ["b1"] }),
          question("B", "answered", { source: "context", context_label: "Report" }),
          question("C", "partly_answered", { missing: "The rest." }),
          question("D", "not_found"),
          question("E", "not_applicable"),
        ],
      },
    ]),
  );
  assert.equal(counts.total, 5);
  assert.equal(
    counts.answered + counts.partlyAnswered + counts.notFound + counts.notApplicable,
    counts.total,
  );
});

test("a partial is counted, and its provenance counted with the answers", () => {
  // Whether an answer can be checked is the same question for a partial, so a partial
  // read from a document belongs in `cited` alongside a whole one.
  const counts = countStates(
    review([
      {
        id: "cd",
        label: "CD",
        questions: [
          question("A", "partly_answered", {
            source: "document",
            cited_block_ids: ["b1"],
            missing: "Zone IVb data.",
          }),
          question("B", "partly_answered", {
            source: "context",
            context_label: "Report",
            missing: "The VVM category.",
          }),
        ],
      },
    ]),
  );
  assert.equal(counts.partlyAnswered, 2);
  assert.equal(counts.cited, 1);
  assert.equal(counts.fromContext, 1);
  assert.equal(counts.answered, 0);
});

test("the count row covers exactly the four states and nothing more", () => {
  // Two states once existed that were derived from a guess about which document could
  // answer a question; if either returns, this fails rather than the row silently
  // ceasing to add up. `partlyAnswered` is not one of them — it is an observation of
  // the supplied material, and it exists because the bank's questions are compound.
  const counts = countStates(
    review([{ id: "cd", label: "CD", questions: [question("A", "not_found")] }]),
  );
  assert.deepEqual(Object.keys(counts).sort(), [
    "answered",
    "cited",
    "fromContext",
    "notApplicable",
    "notFound",
    "partlyAnswered",
    "total",
  ]);
});

test("answered is split by whether the answer can be checked", () => {
  const counts = countStates(
    review([
      {
        id: "cd",
        label: "CD",
        questions: [
          question("A", "answered", { source: "document", cited_block_ids: ["b1"] }),
          question("B", "answered", { source: "context", context_label: "Report" }),
          question("C", "answered", { source: "context", context_label: "Report" }),
        ],
      },
    ]),
  );
  assert.equal(counts.answered, 3);
  assert.equal(counts.cited, 1);
  assert.equal(counts.fromContext, 2);
  assert.equal(counts.cited + counts.fromContext, counts.answered);
});

test("the routing is by discipline, which the question bank guarantees", () => {
  const groups = groupedByDiscipline(
    review([
      { id: "cmc", label: "CMC", questions: [question("C1", "not_found")] },
      {
        id: "cd",
        label: "CD",
        questions: [
          question("D1", "answered", { source: "document", cited_block_ids: ["b"] }),
        ],
      },
      {
        id: "pv",
        label: "Drug Safety",
        questions: [question("P1", "not_found"), question("P2", "not_found")],
      },
    ]),
    "not_found",
  );
  // CD is absent rather than present at zero: a heading with no rows under it is
  // noise, and the count is intrinsic to the group.
  assert.deepEqual(
    groups.map((group) => [group.label, group.questions.length]),
    [["CMC", 1], ["Drug Safety", 2]],
  );
});

test("groups keep bank order, and so do the questions inside them", () => {
  const groups = groupedByDiscipline(
    review([
      {
        id: "cmc",
        label: "CMC",
        questions: [question("C1", "not_found"), question("C2", "not_found")],
      },
      { id: "cd", label: "CD", questions: [question("D1", "not_found")] },
    ]),
    "not_found",
  );
  assert.deepEqual(
    groups.flatMap((group) => group.questions.map((q) => q.id)),
    ["C1", "C2", "D1"],
  );
});

test("the required count is the number that can hold a gate", () => {
  // The bank states `required` or `anticipatory` for every question, so this is read
  // from the source rather than judged. An unanswered anticipatory question is early
  // warning about the next gate, not a shortfall at this one.
  const held = review([
    {
      id: "cp",
      label: "Clinical Pharmacology",
      questions: [
        question("A", "not_found"),
        question("B", "not_found", { requirement: "anticipatory" }),
        question("C", "not_found", { requirement: "anticipatory" }),
        question("D", "answered", { source: "document", cited_block_ids: ["b1"] }),
      ],
    },
  ]);
  assert.equal(countRequiredInState(held, "not_found"), 1);
  assert.equal(questionsInState(held, "not_found").length, 3);
  assert.equal(countRequiredInState(held, "answered"), 1);
});

test("a state nothing is in counts zero rather than throwing", () => {
  const held = review([
    { id: "cp", label: "Clinical Pharmacology", questions: [question("A", "answered")] },
  ]);
  assert.equal(countRequiredInState(held, "partly_answered"), 0);
});

test("only questions in the asked-for state are returned", () => {
  const entries = questionsInState(
    review([
      {
        id: "cd",
        label: "Clinical Development",
        questions: [
          question("A", "not_found", { statement: "No stopping criteria are stated." }),
          question("B", "answered", { source: "document", cited_block_ids: ["b1"] }),
          question("C", "not_applicable"),
        ],
      },
    ]),
    "not_found",
  );
  assert.deepEqual(
    entries.map((entry) => entry.question.id),
    ["A"],
  );
});

test("questionsInState keeps bank order and names the discipline", () => {
  const entries = questionsInState(
    review([
      {
        id: "cmc",
        label: "CMC",
        questions: [
          question("C1", "not_found"),
          question("C2", "answered", { source: "document", cited_block_ids: ["b"] }),
        ],
      },
      { id: "cd", label: "CD", questions: [question("D1", "not_found")] },
    ]),
    "not_found",
  );
  assert.deepEqual(
    entries.map((entry) => [entry.discipline, entry.question.id]),
    [["CMC", "C1"], ["CD", "D1"]],
  );
});
