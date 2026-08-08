import type { GateReview, QuestionAssessment } from "./api.ts";

/**
 * What Expert counts, and how its result view slices the questions.
 *
 * There is no `PriorityItem` selector here. Expert declines the shared
 * `PriorityPanel` — see the note at its call site in `app/expert/page.tsx` — because
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
export const EXPERT_ORDER_NOTE =
  "Wording is Expert's. The order is not: questions appear in the order the "
  + "question bank asks them, discipline by discipline. Nothing here is ranked.";

export const EXPERT_EMPTY_MESSAGE =
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
 * Documents not uploaded that unanswered questions are usually answered by.
 *
 * A suggestion, not an accounting. It reads the bank's `likely_in` hint, which is a
 * judgment rather than something the source document states, so it says "usually" and
 * never claims a question would have been answered. Every one of these questions *was*
 * assessed against what was supplied, and genuinely was not answered there.
 *
 * Read off the questions rather than from a list of document types this module knows,
 * which would put a copy of the source-type vocabulary in the web layer where it could
 * disagree with the configs that own it.
 */
export function suggestedDocuments(
  review: GateReview,
): { sourceType: string; count: number }[] {
  const uploaded = new Set(review.documents.map((document) => document.source_type));
  const counts = new Map<string, number>();
  for (const { question } of questionsInState(review, "not_found")) {
    for (const sourceType of question.likely_in) {
      if (uploaded.has(sourceType)) continue;
      counts.set(sourceType, (counts.get(sourceType) ?? 0) + 1);
    }
  }
  return [...counts.entries()]
    .map(([sourceType, count]) => ({ sourceType, count }))
    .sort((a, b) => b.count - a.count || a.sourceType.localeCompare(b.sourceType));
}
