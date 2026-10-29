"use client";

import { SignalHelp, type SignalTopic } from "@/components/ui/signal-help";

/**
 * Drafter's vocabulary. Each topic exists because a reader can otherwise take a suggestion
 * for a finding, blend the two kinds of evidence, or read the figures as a recommendation.
 */
export type DrafterSignalTopic = "suggestion" | "basis" | "figures";

const TOPICS: Record<DrafterSignalTopic, SignalTopic> = {
  suggestion: {
    promptRef: { tool: "drafter", stage: "suggest" },
    title: "Suggestion",
    summary: "A proposed target for one variable, from the evidence listed with it.",
    detail:
      "A range gives a minimum and a preferred value; a statement gives one requirement in words. Not enough evidence means the sources found could not support either. A suggestion is a starting point for the team, not a finding about any document.",
  },
  basis: {
    promptRef: { tool: "drafter", stage: "evidence" },
    title: "Comparable products and published guidance",
    summary: "Two kinds of evidence, kept apart: what has been done, and what is being asked for.",
    detail:
      "Comparable products are what existing or investigational products achieved. Published guidance is what a target profile or guideline asks of a new one. Every quote is the source's own words, and each suggestion says which kind it leans on.",
  },
  figures: {
    title: "Figures",
    summary: "Comparable products' values, described per stated unit, only from sources quoted word for word.",
    detail:
      "Values in different units are listed separately and never converted. Values sharing a unit may measure different things, and one product may appear in several sources, so read them against the evidence listed. They are not a probability that a target will be met.",
  },
};

export const DRAFTER_TOPIC_LIST: readonly SignalTopic[] = Object.values(TOPICS);

export function DrafterSignalHelp() {
  return (
    <SignalHelp
      title="How to read this draft"
      intro="Drafter suggests a target for each iTPP variable of the product type. Every suggestion cites what comparable products achieved and what published guidance asks; export them to Word or Excel and edit them into your iTPP."
      topics={DRAFTER_TOPIC_LIST as SignalTopic[]}
    />
  );
}
