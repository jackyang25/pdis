"use client";

import {
  SignalHelp,
  SignalLabel,
  type SignalTopic,
} from "@/components/ui/signal-help";

/**
 * Screener's vocabulary. The wording is Screener's; the popover behaviour is shared
 * with Inspector and Scout through `ui/signal-help`.
 *
 * Four topics, and each exists because a reader can otherwise draw the wrong conclusion
 * from something on the page: that a question the documents do not answer is a fault,
 * that every answer can be checked, that every open question weighs the same, or that a
 * count can be blended into a score.
 */

export type ScreenerSignalTopic =
  | "state"
  | "source"
  | "requirement"
  | "denominator";

const TOPICS: Record<ScreenerSignalTopic, SignalTopic> = {
  state: {
    promptRef: { tool: "screener", stage: "triage" },
    title: "State",
    summary:
      "What became of one question: answered, partly answered, not found, or not applicable.",
    detail:
      "The questions are compound, so they are judged clause by clause: answered means every part is answered, partly answered means some clause is not, and each one names which. Not found means nothing you supplied speaks to it. Not applicable is the bank's own decision, never the model's.",
  },
  source: {
    promptRef: { tool: "screener", stage: "triage" },
    title: "Source",
    summary: "Whether an answer can be checked, or only attributed.",
    detail:
      "An answer read from an uploaded document cites the exact passage, so you can open it and confirm it. An answer read from attached context cannot, because context is never chunked or cited. Both are the model's reading; only one is checkable.",
  },
  requirement: {
    // No promptRef: the bank states it for every question and no model reads it.
    title: "Required at this gate",
    summary:
      "Whether this gate expects the question answered now, or expects it to be forming.",
    detail:
      "The bank states this for every question, and it is what makes an open question actionable: a required one the documents do not answer is what holds a gate up. An anticipatory one is early warning, so leaving it open is a prompt for the next conversation rather than a shortfall. Only required questions carry the badge.",
  },
  denominator: {
    title: "The count",
    summary: "Every question the gate asks appears, in every run.",
    detail:
      "The states sum to the total, so the row checks itself and nothing is filtered out of the denominator. There is no combined coverage figure: one number blending “the document says it”, “it says half of it” and “nobody has asked yet” would tell a committee something untrue.",
  },
};

/** Publication order, shared by the tooltips and the documentation panel. */
export const SCREENER_TOPIC_LIST: readonly SignalTopic[] = Object.values(TOPICS);

export function ScreenerSignalLabel({
  topic,
  children,
  className,
}: {
  topic: ScreenerSignalTopic;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <SignalLabel topic={TOPICS[topic]} className={className}>
      {children}
    </SignalLabel>
  );
}

export function ScreenerSignalHelp() {
  return (
    <SignalHelp
      title="How to read this triage"
      intro="Screener sorts the questions one stage gate asks. It does not answer them: every question that applies is read against everything you supplied, what is answered is cited to a passage, and what is not is reported as not found alongside the discipline that owns it."
      topics={SCREENER_TOPIC_LIST as SignalTopic[]}
    />
  );
}
