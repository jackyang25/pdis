import type { GateReview, QuestionAssessment } from "./api.ts";
import { QUESTION_REQUIREMENT_LABEL, QUESTION_STATE_LABEL } from "./api.ts";
import type { PriorityFinding } from "./priorities.ts";
import { matchesQuery, normalizeQuery } from "./result-search.ts";

/**
 * What Screener counts, how its result view slices the questions, and how its result is
 * read for the priority card.
 */

export const SCREENER_PRIORITY_FOCUS =
  "Questions this gate requires that the material leaves unanswered or only partly "
  + "answered, and the disciplines that own them; anticipatory gaps after those.";

/**
 * One finding per gate question, every state included.
 *
 * The question is the subject in full: it is what a reader closes, and a summary of it
 * would be a second wording that could disagree with the bank. What a partial answer still
 * leaves open is the model's own sentence, labelled so it is not read as the answer.
 */
export function screenerPriorityFindings(review: GateReview): PriorityFinding[] {
  return review.disciplines.flatMap((discipline) =>
    discipline.questions.map((question) => ({
      id: question.id,
      subject: question.text,
      group: discipline.label,
      verdicts: [
        QUESTION_STATE_LABEL[question.state],
        QUESTION_REQUIREMENT_LABEL[question.requirement],
      ],
      statements: [
        question.statement,
        question.missing ? `Still open: ${question.missing}` : "",
      ],
      blockIds: question.cited_block_ids,
    })),
  );
}

/**
 * Why this order, in the reader's words. Shown beneath the list.
 *
 * It no longer says "each one also appears in its discipline below", because the
 * duplicate list it referred to is gone.
 */
export const SCREENER_ORDER_NOTE =
  "Within each discipline, Required questions appear before Anticipatory questions. "
  + "Each group keeps the question bank's order.";

export const SCREENER_EMPTY_MESSAGE =
  "Every question this gate asks is answered by the material supplied.";

/**
 * How many questions sit in each state, derived on read.
 *
 * Never stored on the result: a carried count is a second authority that can
 * disagree with the list it summarises. The values sum to the total, which is what
 * makes the header row self-verifying.
 */
export type StateCounts = {
  answered: number;
  partlyAnswered: number;
  notFound: number;
  notApplicable: number;
  total: number;
};

export function countStates(review: GateReview): StateCounts {
  const counts: StateCounts = {
    answered: 0,
    partlyAnswered: 0,
    notFound: 0,
    notApplicable: 0,
    total: 0,
  };
  for (const question of allQuestions(review)) {
    counts.total += 1;
    switch (question.state) {
      case "answered":
        counts.answered += 1;
        break;
      case "partly_answered":
        counts.partlyAnswered += 1;
        break;
      case "not_found":
        counts.notFound += 1;
        break;
      case "not_applicable":
        counts.notApplicable += 1;
        break;
    }
  }
  return counts;
}

export function allQuestions(review: GateReview): QuestionAssessment[] {
  return review.disciplines.flatMap((discipline) => discipline.questions);
}

/** Questions in one state, kept in bank order, with the discipline they belong to. */
export function questionsInState(
  review: GateReview,
  state: QuestionAssessment["state"],
): { discipline: string; question: QuestionAssessment }[] {
  return review.disciplines.flatMap((discipline) =>
    discipline.questions
      .filter((question) => question.state === state)
      .map((question) => ({ discipline: discipline.label, question })),
  );
}

/**
 * Questions in one state, grouped by the discipline that owns them.
 *
 * The discipline is the routing, and it is the one grouping the source question bank
 * guarantees. Grouping rather than listing per-discipline counts beside the heading:
 * that count was a third representation of the same data — the coverage strip shows it
 * visually and the group headings show it structurally — and as a single run-on string
 * of eight labels it overflowed its row and was clipped mid-word.
 *
 * Empty groups are dropped, so a discipline with nothing in this state does not render
 * a heading with no rows under it.
 */
export function groupedByDiscipline(
  review: GateReview,
  state: QuestionAssessment["state"],
  query = "",
): { id: string; label: string; questions: QuestionAssessment[] }[] {
  // The question text and the sentence about it, not the discipline label: a reader
  // searching "shelf life" wants the question, and matching the label instead would
  // return every question in a discipline whose name happened to contain the word.
  //
  // A discipline with nothing left disappears. It is a container, and one standing empty
  // says a category exists rather than that a result does.
  const normalized = normalizeQuery(query);
  return review.disciplines
    .map((discipline) => ({
      id: discipline.id,
      label: discipline.label,
      questions: discipline.questions.filter(
        (question) =>
          question.state === state
          && matchesQuery(normalized, question.text, question.statement, question.missing),
      ).sort((a, b) => Number(b.requirement === "required") - Number(a.requirement === "required")),
    }))
    .filter((group) => group.questions.length > 0);
}

/**
 * How many questions in one state the gate requires answered now.
 *
 * The number that decides whether a gate can be held. The bank states `required` or
 * `anticipatory` for every question, so this is read from the source rather than judged:
 * an unanswered required question holds the review up, and an unanswered anticipatory one
 * is early warning about the next gate.
 *
 * There used to be a panel here suggesting which document to upload next, built from a
 * per-question guess about where each answer usually lives. No source stated it, and the
 * bank this tool now carries states something better in its place.
 */
export function countRequiredInState(
  review: GateReview,
  state: QuestionAssessment["state"],
): number {
  return questionsInState(review, state).filter(
    ({ question }) => question.requirement === "required",
  ).length;
}
