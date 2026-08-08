"use client";

import type { GateReview, QuestionAssessment, QuestionState } from "@/lib/api";

/**
 * The whole gate at a glance: one cell per question, one row per discipline.
 *
 * Deliberately not a tree. The hierarchy is a fixed taxonomy — eight disciplines of
 * ten questions, identical for every run of a gate — so a tree diagram would differ
 * between runs only in its colours, which makes it a grid wearing a tree's costume.
 * The panels below already group by discipline; this exists to answer the one thing
 * they cannot at a glance, which is where the thin disciplines are.
 *
 * Nothing here is a second opinion. Every cell reads the state the result carries, in
 * bank order, so the strip cannot disagree with the panels or the counts — and there
 * is deliberately no cell for "probably in the IPDP", because drawing the `likely_in`
 * hint as structure would hand a guess the authority of a layout.
 */

/**
 * One question.
 *
 * A button only when there is somewhere to go. Every cell used to be a button with a
 * hover state, so three quarters of the grid invited a click and did nothing — only an
 * answer cited to a passage has anything to open. The title carries the whole claim
 * either way, so the colour is never the only signal, which is the rule the trace
 * emphasis follows too.
 */
function Cell({
  question,
  onSelect,
}: {
  question: QuestionAssessment;
  onSelect?: (question: QuestionAssessment) => void;
}) {
  const tone = TONE[question.state];
  const title = `${question.id} · ${tone.label}${
    question.statement ? ` — ${question.statement}` : ""
  }`;
  const shape = `h-3.5 w-3.5 rounded-[3px] ${tone.cell}`;
  const openable = Boolean(onSelect) && question.cited_block_ids.length > 0;

  if (!openable) {
    return <span title={title} aria-label={title} className={shape} />;
  }
  return (
    <button
      type="button"
      onClick={() => onSelect?.(question)}
      title={`${title} — open the passage`}
      aria-label={`${title}. Open the passage.`}
      className={`${shape} transition-opacity hover:opacity-70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40 motion-reduce:transition-none`}
    />
  );
}

const TONE: Record<QuestionState, { cell: string; label: string }> = {
  answered: {
    cell: "bg-[hsl(var(--tone-success))]",
    label: "answered",
  },
  partly_answered: {
    // Between the two it sits between, and on the caution token rather than a tint of
    // either — a lighter green would read as "nearly answered", which is a judgment
    // about progress this tool does not make.
    cell: "bg-[hsl(var(--tone-warning))]",
    label: "partly answered",
  },
  not_found: {
    // The strongest mark, because it is the actionable one — not because it is a
    // failure. `not_found` says the material did not answer it, nothing more.
    cell: "bg-foreground/45",
    label: "not found",
  },
  not_applicable: {
    cell: "bg-border",
    label: "not applicable",
  },
};

export function ExpertCoverageStrip({
  review,
  onSelect,
}: {
  review: GateReview;
  /** Opens the question. Every cell is reachable by keyboard for the same reason. */
  onSelect?: (question: QuestionAssessment) => void;
}) {
  const present = new Set(
    review.disciplines.flatMap((discipline) =>
      discipline.questions.map((question) => question.state),
    ),
  );

  return (
    <section aria-label="Coverage by discipline">
      <ul className="space-y-1">
        {review.disciplines.map((discipline) => (
          <li key={discipline.id} className="flex items-center gap-3">
            <span
              className="w-40 shrink-0 truncate text-[11px] text-muted-foreground"
              title={discipline.label}
            >
              {discipline.label}
            </span>
            <span className="flex flex-wrap gap-1">
              {discipline.questions.map((question) => (
                <Cell key={question.id} question={question} onSelect={onSelect} />
              ))}
            </span>
          </li>
        ))}
      </ul>

      <p className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-[10px] text-muted-foreground">
        {(Object.keys(TONE) as QuestionState[])
          .filter((state) => present.has(state))
          .map((state) => (
            <span key={state} className="inline-flex items-center gap-1.5">
              <span className={`h-2.5 w-2.5 rounded-[2px] ${TONE[state].cell}`} />
              {TONE[state].label}
            </span>
          ))}
        <span>Bank order, left to right. Every question the gate asks appears.</span>
      </p>
    </section>
  );
}
