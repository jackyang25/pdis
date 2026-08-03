"use client";

import {
  SignalHelp,
  SignalLabel,
  type SignalTopic,
} from "@/components/ui/signal-help";

/**
 * Scout's vocabulary. The wording is Scout's; the popover behaviour is shared
 * with every other tool through `ui/signal-help`.
 */

export type ScoutSignalTopic =
  | "relationships"
  | "grounding"
  | "alignment"
  | "precedent";

const TOPICS: Record<ScoutSignalTopic, SignalTopic> = {
  relationships: {
    title: "Evidence relationships",
    summary: "How each external insight relates to the document target. The numbers count insights, not sources.",
    detail: "Conflicts means an insight contradicts the target. Adds context is relevant but neither proves nor disputes it. Supports means it reinforces the target. Unrelated does not meaningfully bear on it.",
    promptRef: { tool: "scout", stage: "drift_classifier" },
  },
  grounding: {
    title: "Evidence · Grounding",
    summary: "The overall assessment of how well external evidence justifies the document target.",
    detail: "The source count is the evidence selected for this assessment; it does not need to equal the relationship counts.",
    promptRef: { tool: "scout", stage: "evidence_assessor" },
  },
  alignment: {
    title: "Evidence · Quantitative calibration",
    summary: "A numeric document claim compared only with source-quoted, claim-compatible, deduplicated measurements.",
    detail: "The count shows how many admitted comparators meet the target. Prose-derived numbers require review before entering the distribution. Statistics describe the admitted cohort only; they are not confidence intervals or forecasts.",
    promptRef: { tool: "scout", stage: "conformity" },
  },
  precedent: {
    title: "Precedent",
    summary: "Two separate signals: how directly prior work matches the target, and what outcome that work reported.",
    detail: "Coverage is Direct, Adjacent, None found, or Unknown. Outcome is Favorable, Mixed, Unfavorable, or Unknown.",
    promptRef: { tool: "scout", stage: "precedent_classifier" },
  },
};

/** Publication order, shared by the tooltips and the documentation panel. */
export const SCOUT_TOPIC_LIST: readonly SignalTopic[] = Object.values(TOPICS);

export function ScoutSignalLabel({
  topic,
  children,
  className,
}: {
  topic: ScoutSignalTopic;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <SignalLabel topic={TOPICS[topic]} className={className}>
      {children}
    </SignalLabel>
  );
}

export function ScoutSignalHelp() {
  return (
    <SignalHelp
      title="How to read Scout signals"
      intro="These columns answer different questions and should not be combined into one grade."
      topics={Object.values(TOPICS)}
    />
  );
}
