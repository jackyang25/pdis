"use client";

import { SignalHelp, type SignalTopic } from "@/components/ui/signal-help";

/**
 * Scout's vocabulary. The wording is Scout's; the popover behaviour is shared
 * with every other tool through `ui/signal-help`.
 */

export type ScoutSignalTopic =
  | "relationships"
  | "grounding"
  | "measurable"
  | "precedent";

/**
 * Scout's four result axes, in one sentence each.
 *
 * Titles match the section headings they explain, exactly. They had drifted to "Evidence
 * relationships" and "Evidence · Grounding" while the interface rendered "External
 * evidence" and "Grounding", so a reader opening a tooltip was told a different name for
 * the thing they had clicked.
 *
 * Every summary opens by naming the axis's *unit*, because that is the only thing that
 * tells these four apart. Relationship is one insight; grounding is one field; measurable
 * targets are one number; precedent is one body of prior work. Written any other way, all
 * four read as "external evidence about the target" and a reader cannot see the difference.
 */
const TOPICS: Record<ScoutSignalTopic, SignalTopic> = {
  relationships: {
    title: "Relation to document target",
    summary:
      "One insight at a time, and what each does to the target. Counts are insights, not sources.",
    detail:
      "Conflicts contradicts the target. Supports reinforces it. Adds context bears on it without settling it. Unrelated does not speak to it.",
    promptRef: { tool: "scout", stage: "drift_classifier" },
  },
  grounding: {
    title: "Grounding",
    summary:
      "One verdict for the whole field: how well outside evidence justifies the target.",
    detail:
      "Well grounded, Partly grounded, Thinly grounded, Unsupported, or Grounding unknown. The count is the evidence this verdict rests on, and it need not match the relationship counts.",
    promptRef: { tool: "scout", stage: "evidence_assessor" },
  },
  measurable: {
    title: "Measurable targets",
    summary:
      "One number at a time, compared with measurements of the same quantity from outside.",
    detail:
      "Numbers are read only from passages a resolved target cites, so a field whose target could not be read has none. A measurement joins the comparison only if it measures the same quantity in the same unit and is quoted from its source. The statistics describe that cohort alone: they are not confidence intervals, population estimates, or probabilities of success.",
    promptRef: { tool: "scout", stage: "conformity" },
  },
  precedent: {
    title: "Precedent",
    summary:
      "Whether anyone has done this before, and how it went. Two separate readings.",
    detail:
      "Coverage is Direct precedent, Adjacent precedent, No precedent found, or Precedent unknown. Outcome is Favorable outcome, Mixed outcome, Unfavorable outcome, or Outcome unknown. A close match can still have gone badly, so neither implies the other.",
    promptRef: { tool: "scout", stage: "precedent_classifier" },
  },
};

/** Publication order, shared by the tooltips and the documentation panel. */
export const SCOUT_TOPIC_LIST: readonly SignalTopic[] = Object.values(TOPICS);

export function ScoutSignalHelp() {
  return (
    <SignalHelp
      title="How to read Scout signals"
      intro="Each answers a different question about a different unit. None is a grade, and they do not combine into one."
      topics={Object.values(TOPICS)}
    />
  );
}
