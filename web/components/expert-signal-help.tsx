"use client";

import {
  SignalHelp,
  SignalLabel,
  type SignalTopic,
} from "@/components/ui/signal-help";

/**
 * Expert's vocabulary. The wording is Expert's; the popover behaviour is shared
 * with Inspector and Scout through `ui/signal-help`.
 *
 * Five topics, and each exists because a reader can otherwise draw the wrong
 * conclusion from something on the page: that a question the documents do not answer
 * is a fault, that every answer can be checked, that a hint is a finding, that a count
 * can be blended into a score, or — the one that is simply an acronym — that `PQ` is
 * self-explanatory.
 */

export type ExpertSignalTopic = "state" | "source" | "hint" | "pq" | "denominator";

const TOPICS: Record<ExpertSignalTopic, SignalTopic> = {
  state: {
    promptRef: { tool: "expert", stage: "triage" },
    title: "State",
    summary:
      "What became of one question: answered, partly answered, not found, or not applicable.",
    detail:
      "These questions are compound — most ask three to five things in one sentence — so they are judged clause by clause. Answered means every part is answered. Partly answered means some parts are and some are not, and it carries a line saying exactly what is still not stated; that line is the specific thing to ask the grantee for, and it is the most actionable output here. Not found means the question was read against everything you supplied and nothing addressed it — nothing more than that. It is not a judgment about whose fault it is, and not a claim that one of your documents should have contained it: many of these questions ask about operational facts or matters of judgment that no profile or plan would ever carry, and this tool cannot tell those apart from a real omission. What it can tell you is which discipline owns the question. Not applicable means the question's own text restricts it to a different intervention class, so no model read it and it is not a shortfall of any kind. Partly answered is not a progress bar and there is no score: 40 partial answers is not 'half done'.",
  },
  source: {
    promptRef: { tool: "expert", stage: "triage" },
    title: "Source",
    summary: "Whether an answer can be checked, or only attributed.",
    detail:
      "This applies to a partial answer exactly as it does to a whole one. An answer read from an uploaded document cites the exact passage, so you can open it and confirm it. An answer read from context you attached for the run names which item it came from and nothing more, because that text is never stored — the file is read once, goes into the request, and is gone. So the label is the whole record: reopening this result later shows the name with nothing behind it. Both are genuinely answered and both are counted the same way; what differs is whether anyone can verify it afterwards. A run answered mostly from attached context is a different situation from one answered from the documents, which is why the two are counted separately.",
  },
  pq: {
    // No promptRef: the marker is transcribed from the question bank, not produced
    // by a model, and `SignalHelp` omits the instructions link when a value is
    // deterministic rather than authored.
    title: "PQ",
    summary:
      "A WHO prequalification question, carried inside its discipline's ten at Decision to Launch.",
    detail:
      "Prequalification is WHO's own assessment, separate from the reference agency's approval, and for most of the world it is the actual launch gate: most donor-funded procurement is contractually contingent on the listing rather than on registration. So a launch review that looks settled on registration can still be blocked on procurement, and these are the questions that decide which. They appear only at Decision to Launch, because that is where the source bank places them, and they are not a separate list — each sits inside its discipline's ten and is triaged like any other question.",
  },
  hint: {
    title: "Usually answered in",
    summary: "Where an answer of this kind normally lives. A hint, and it may be wrong.",
    detail:
      "The question bank is a list of questions for reviewers to ask people. It says nothing about iTPPs, cTPPs or IPDPs, so this hint is not from your source document — it is a judgment about where an answer of this kind usually sits. It is shown so you can decide which document to open, or which one to upload next. It decided nothing: the question was read against everything you supplied regardless, and a wrong hint costs you a misleading suggestion rather than a wrong result. Nothing tells the model about it either, so it cannot steer the search.",
  },
  denominator: {
    title: "The count",
    summary: "Every question the gate asks appears, in every run.",
    detail:
      "The states sum to the total, so the row of counts checks itself. Nothing is filtered out of the denominator, which is what lets two runs on one gate be compared line by line and what makes a count safe to quote in a review. There is no combined coverage figure, and no way to add the states into a score: one number blending 'the document says it', 'it says half of it', and 'nobody has asked yet' would tell a committee something untrue.",
  },
};

/** Publication order, shared by the tooltips and the documentation panel. */
export const EXPERT_TOPIC_LIST: readonly SignalTopic[] = Object.values(TOPICS);

export function ExpertSignalLabel({
  topic,
  children,
  className,
}: {
  topic: ExpertSignalTopic;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <SignalLabel topic={TOPICS[topic]} className={className}>
      {children}
    </SignalLabel>
  );
}

export function ExpertSignalHelp() {
  return (
    <SignalHelp
      title="How to read this triage"
      intro="Expert sorts the questions this gate asks. It does not answer them: every question that applies is read against everything you supplied, what is answered is cited to a passage, and what is not is reported as not found alongside the discipline that owns it."
      topics={EXPERT_TOPIC_LIST as SignalTopic[]}
    />
  );
}
