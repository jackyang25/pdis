import type { GateReview, QuestionAssessment } from "./api.ts";

/**
 * What Screener counts, and how its result view slices the questions.
 *
 * There is no `PriorityItem` selector here. Screener declines the shared
 * `PriorityPanel` — see the note at its call site in `app/screener/page.tsx` — because
 * a 40-60 word gate question has nowhere to go in that shape, and the panel restated
 * a list that was already flat. `questionsInState` feeds the panels instead, which
 * carry the question alongside the statement about it.
 */

/**
 * Why this order, in the reader's words. Shown beneath the list.
 *
 * It no longer says "each one also appears in its discipline below", because the
 * duplicate list it referred to is gone.
 */
export const SCREENER_ORDER_NOTE =
  "Wording is Screener's. The order is not: questions appear in the order the "
  + "question bank asks them, discipline by discipline. Nothing here is ranked.";

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
  /** Of the answered and partial, how many cite a passage — the checkable ones. */
  cited: number;
  /** Of the answered and partial, how many name a pasted context item instead. */
  fromContext: number;
  notFound: number;
  notApplicable: number;
  total: number;
};

export function countStates(review: GateReview): StateCounts {
  const counts: StateCounts = {
    answered: 0,
    partlyAnswered: 0,
    cited: 0,
    fromContext: 0,
    notFound: 0,
    notApplicable: 0,
    total: 0,
  };
  for (const question of allQuestions(review)) {
    counts.total += 1;
    switch (question.state) {
      case "answered":
        counts.answered += 1;
        if (question.source === "context") counts.fromContext += 1;
        else counts.cited += 1;
        break;
      case "partly_answered":
        counts.partlyAnswered += 1;
        // Provenance is the same question for a partial: an answer read from a
        // document can be checked, one from pasted context cannot.
        if (question.source === "context") counts.fromContext += 1;
        else counts.cited += 1;
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
): { id: string; label: string; questions: QuestionAssessment[] }[] {
  return review.disciplines
    .map((discipline) => ({
      id: discipline.id,
      label: discipline.label,
      questions: discipline.questions.filter((question) => question.state === state),
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
