"use client";

import {
  SignalHelp,
  SignalLabel,
  type SignalTopic,
} from "@/components/ui/signal-help";
import type { DimensionName } from "@/lib/api";

/**
 * Inspector's vocabulary. The wording is Inspector's; the popover behaviour is
 * shared with Scout through `ui/signal-help`.
 *
 * The three dimensions are deliberately independent, and the most common
 * misreading is treating a low grade on one as a low grade overall - so each
 * entry says what its dimension does *not* judge.
 */

export type InspectorSignalTopic = DimensionName | "presence" | "consistency";

const TOPICS: Record<InspectorSignalTopic, SignalTopic> = {
  completeness: {
    promptRef: { tool: "inspector", stage: "completeness" },
    title: "Completeness",
    summary: "Is the content the rubric asks for actually in the document?",
    detail:
      "Judges presence only. A target can be fully present and still score badly on rigor for being vague, so a high completeness grade is not a statement about quality.",
  },
  adherence: {
    promptRef: { tool: "inspector", stage: "adherence" },
    title: "Template adherence",
    summary: "Does the content follow the rubric's expected structure and naming?",
    detail:
      "Judges form, not substance: section and variable names matching the rubric, expected columns present, no template tokens left behind. Well-formed content can still be wrong.",
  },
  rigor: {
    promptRef: { tool: "inspector", stage: "rigor" },
    title: "Rigor",
    summary: "Is the content that is present specific, measurable, and sound?",
    detail:
      "Judges quality only, never presence or formatting. A target should be testable — a value with units or a clear pass/fail — rather than language like 'robust' that has no checkable meaning. Judged against the document's stage: an early profile is held to a different bar than a candidate specification.",
  },
  presence: {
    promptRef: { tool: "inspector", stage: "completeness" },
    title: "Presence",
    summary: "How much of a required variable the document actually supplies.",
    detail:
      "Not present means nothing is there, so it cites no passage. Placeholder means a token such as <<TBD>> is sitting where the value belongs. Partially filled means some of it is stated. These need different fixes, which is why they are labelled apart.",
  },
  consistency: {
    promptRef: { tool: "inspector", stage: "consistency" },
    title: "Cross-section consistency",
    summary: "Do two different sections state claims that cannot both hold?",
    detail:
      "Only conflicts spanning more than one section appear here — a problem inside a single section is graded by the three dimensions instead. This check compares your document with itself; it never consults outside evidence.",
  },
};

/**
 * Grades are one scale across all three dimensions, so they are explained once
 * rather than repeated per column.
 */
const GRADE_TOPIC: SignalTopic = {
  title: "Grades",
  summary: "A to F on each dimension, plus N/A when the rubric does not apply.",
  detail:
    "A section grade averages its variables and a document grade weights its sections by the rubric's own weights, so the three document letters are roll-ups, never a single overall score. There is deliberately no combined grade.",
};

/** Publication order, shared by the tooltips and the documentation panel. */
export const INSPECTOR_TOPIC_LIST: readonly SignalTopic[] = [
  ...Object.values(TOPICS),
  GRADE_TOPIC,
];

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
      title="How to read Inspector grades"
      intro="The three dimensions answer different questions about the same content and are never combined into one score."
      topics={[...Object.values(TOPICS), GRADE_TOPIC]}
    />
  );
}
