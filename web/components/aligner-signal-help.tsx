"use client";

import {
  SignalHelp,
  SignalLabel,
  type SignalTopic,
} from "@/components/ui/signal-help";

/**
 * Aligner's vocabulary. The wording is Aligner's; the popover behaviour is shared with
 * Inspector, Scout and Expert through `ui/signal-help`.
 *
 * Five topics, each because a reader can otherwise draw a wrong conclusion from
 * something on the page: that a comparison runs both ways, that a requirement is
 * something Aligner decided, that "not addressed" means a document is deficient, that a
 * flagged passage means the verdict beside it is wrong, or that the verdicts can be
 * added into a compliance score.
 */

export type AlignerSignalTopic =
  | "verdict"
  | "requirement"
  | "direction"
  | "chain"
  | "denominator";

const TOPICS: Record<AlignerSignalTopic, SignalTopic> = {
  verdict: {
    promptRef: { tool: "aligner", stage: "compare" },
    title: "Verdict",
    summary:
      "What one document does with one requirement: meets, exceeds, falls short, not comparable, or not addressed.",
    detail:
      "The five are read against the bar, not against each other. Meets and exceeds both clear it, and they are kept apart because a candidate well past its target is worth knowing about — it may mean the target is stale, or the candidate is over-specified. Falls short and not comparable both carry a line naming what is still to close, and that line is the specific thing to take back to whoever wrote the document. Not comparable exists so vagueness is not reported as a shortfall: a qualitative claim against a numeric bar — 'convenient dosing' where the profile asks for annual dosing — is neither worse nor silent, and calling it either would be a judgement the text does not support. Not addressed means this document says nothing on the subject, which is often a question about which document should have carried it rather than a deficiency in this one.",
  },
  requirement: {
    promptRef: { tool: "aligner", stage: "requirements" },
    title: "Requirement",
    summary:
      "One thing the reference document asks for, in its own words, cited to the passage that asks it.",
    detail:
      "Aligner does not decide what matters. Each requirement is read out of the reference document and cites the passage it came from, so the bar is checkable before any argument about whether it was met. Compound sentences are split: a line setting a shelf life, a storage temperature and a presentation becomes three requirements, because one verdict cannot honestly cover three separate facts. A requirement is a quotation of a demand, never an opinion about it — nothing here rates whether the bar is sensible.",
  },
  direction: {
    title: "Direction",
    summary: "A comparison runs one way. The reference document sets the bar.",
    detail:
      "This is not a diff. An iTPP-to-cTPP comparison asks whether the candidate clears the bar the Foundation set; a cTPP-to-IPDP comparison asks whether the plan delivers what the candidate commits to. The direction is why 'exceeds' and 'falls short' are different verdicts at all — a symmetric comparison can only say the two documents differ, which is the same word for a candidate that beat its target and one that missed it by years. Which pairs compare, and in which direction, is configuration: a document can sit on either side, and the cTPP does both in a three-document run.",
  },
  chain: {
    // No promptRef: no model produced this. It is the two comparisons' own citations,
    // compared, and `SignalHelp` omits the instructions link for a deterministic value.
    title: "Flagged upstream",
    summary:
      "This passage is cited by an earlier comparison too, which left it unsettled.",
    detail:
      "With three documents the middle one is in both comparisons: measured against the first, authoritative over the third. So a plan can faithfully deliver a commitment that itself falls short of the profile, and every verdict involved is correct — the plan really does meet the cTPP. Reading the second comparison alone, it is all good news. This mark is the two findings linked at the passage they both cite, so the situation is visible without holding two lists side by side. It does not change or contradict the verdict beside it, and no model produced it: the link is one block id appearing on both sides. It is a claim about the passage rather than about the requirement, because a paragraph can carry several facts and the two comparisons need not have meant the same one. It also under-reports rather than guessing — if the two comparisons cite the commitment in different places, no mark appears.",
  },
  denominator: {
    title: "The count",
    summary: "Every requirement read from a reference document appears, whatever its verdict.",
    detail:
      "The verdicts sum to the total, so the row of counts checks itself, and nothing is filtered out — which is what lets two runs on one pair be compared line by line. There is no compliance score and no percentage: one number blending 'the candidate meets this', 'it beats this', 'it says something that cannot be compared' and 'this document does not cover it' would tell a committee something untrue. The total is also not a fixed list. It is however many requirements this reference document states, so a longer profile has more of them, and two different pairs are not comparable by count.",
  },
};

/** Publication order, shared by the tooltips and the documentation panel. */
export const ALIGNER_TOPIC_LIST: readonly SignalTopic[] = Object.values(TOPICS);

export function AlignerSignalLabel({
  topic,
  children,
  className,
}: {
  topic: AlignerSignalTopic;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <SignalLabel topic={TOPICS[topic]} className={className}>
      {children}
    </SignalLabel>
  );
}

export function AlignerSignalHelp() {
  return (
    <SignalHelp
      title="How to read this comparison"
      intro="Aligner reads what one document requires and checks the other against it, one requirement at a time. It never rates how well either document is written, and it never looks outside them."
      topics={ALIGNER_TOPIC_LIST as SignalTopic[]}
    />
  );
}
