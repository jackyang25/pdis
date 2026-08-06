"use client";

import {
  SignalHelp,
  SignalLabel,
  type SignalTopic,
} from "@/components/ui/signal-help";

/**
 * Inspector's vocabulary. The wording is Inspector's; the popover behaviour is
 * shared with Scout through `ui/signal-help`.
 *
 * Three topics, one per published vocabulary: what a finding is, what a unit's
 * status means, and what the whole-document check covers. There were six, because
 * three internal questions each needed explaining plus a presence scale and a
 * severity scale on top; merging the questions merged their explanations too.
 */

export type InspectorSignalTopic = "finding" | "status" | "consistency";

const TOPICS: Record<InspectorSignalTopic, SignalTopic> = {
  finding: {
    promptRef: { tool: "inspector", stage: "assessment" },
    title: "Finding",
    summary: "One thing to fix, with the reason it was raised.",
    detail:
      "A finding is one problem, one recommendation, and the exact passage it was read from, so a count of findings is a count of things to do. Reasons: Not present means nothing is there. Placeholder left in means a token such as <<TBD>> sits where the value belongs. Does not meet the requirement means content is there and does not satisfy it. Off template means the structure or naming deviates. Not specific enough means the requirement is satisfied but the content is vague. Conflicts with another section comes from the whole-document check. A unit raises each reason at most once, and content that is not present raises nothing else, because there is nothing there to have read.",
  },
  status: {
    promptRef: { tool: "inspector", stage: "assessment" },
    title: "Status",
    summary: "How one rubric unit stands: met, could be stronger, not met, or not applicable.",
    detail:
      "Derived from the findings on that unit alone, so met always means exactly zero findings and no view can show you a different answer. Not met covers content that is absent, a placeholder, or present but not satisfying the requirement. Could be stronger covers content that satisfies the requirement and would be better with more specificity. Not applicable means the rubric itself accepts this being absent, so it is not a shortfall. Nothing here says what a shortfall costs your programme, because that is not something this tool can see: there is no letter grade, no severity scale, and no overall score.",
  },
  consistency: {
    promptRef: { tool: "inspector", stage: "consistency" },
    title: "Cross-section consistency",
    summary: "Do two different sections state claims that cannot both hold?",
    detail:
      "Only conflicts spanning more than one section are reported here, and a conflict must cite passages from at least two of them; that span is what makes it cross-section. A problem inside one section belongs to that unit instead. This check compares your document with itself and never consults outside evidence. If it does not complete, that is reported as its own status rather than as a document with nothing wrong.",
  },
};

/** Publication order, shared by the tooltips and the documentation panel. */
export const INSPECTOR_TOPIC_LIST: readonly SignalTopic[] = Object.values(TOPICS);

export function InspectorSignalLabel({
  topic,
  children,
  className,
}: {
  topic: InspectorSignalTopic;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <SignalLabel topic={TOPICS[topic]} className={className}>
      {children}
    </SignalLabel>
  );
}

export function InspectorSignalHelp() {
  return (
    <SignalHelp
      title="How to read this assessment"
      intro="Inspector checks one document against its authored rubric. Every unit the rubric asks about is assessed, and every finding cites the passage it came from."
      topics={INSPECTOR_TOPIC_LIST as SignalTopic[]}
    />
  );
}
