"use client";

import {
  SignalHelp,
  SignalLabel,
  type SignalTopic,
} from "@/components/ui/signal-help";

/**
 * Aligner's vocabulary. The wording is Aligner's; the popover behaviour is shared with
 * Inspector, Scout and Screener through `ui/signal-help`.
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
      "Meets and exceeds both clear the bar, and are kept apart because a candidate well past its target may mean the target is stale. Not comparable exists so vagueness is not reported as a shortfall: “convenient dosing” against a bar of annual dosing is neither worse nor silent. Not addressed is often a question about which document should have carried the requirement.",
  },
  requirement: {
    promptRef: { tool: "aligner", stage: "requirements" },
    title: "Requirement",
    summary:
      "One thing the reference document asks for, in its own words, cited to the passage that asks it.",
    detail:
      "Aligner does not decide what matters. Each one is read out of the reference document and cites the passage it came from, so the bar is checkable before any argument about whether it was met. Compound sentences are split, because one verdict cannot honestly cover three separate facts.",
  },
  direction: {
    title: "Direction",
    summary: "A comparison runs one way. The reference document sets the bar.",
    detail:
      "The reference document sets the bar and the other is measured against it, so a finding never reads in reverse. The middle document of a three-document run is measured in the first comparison and authoritative in the second.",
  },
  chain: {
    // No promptRef: no model produced this. It is the two comparisons' own citations,
    // compared, and `SignalHelp` omits the instructions link for a deterministic value.
    title: "Flagged upstream",
    summary:
      "This passage is cited by an earlier comparison too, which left it unsettled.",
    detail:
      "A plan can faithfully deliver a commitment that itself falls short: every verdict is correct and the second comparison reads as good news. This is a claim about the passage, not the requirement: a paragraph can carry several facts, so a shared citation does not prove both comparisons meant the same clause.",
  },
  denominator: {
    title: "The count",
    summary: "Every requirement read from a reference document appears, whatever its verdict.",
    detail:
      "Totals are not comparable across comparisons: the denominator is however many requirements that reference document happens to state. There is no compliance score, and nothing is filtered out of the count.",
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
