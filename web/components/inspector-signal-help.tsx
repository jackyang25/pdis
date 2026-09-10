"use client";

import { VERDICTS, VERDICT_DESCRIPTION, VERDICT_LABEL } from "@/lib/api";
import {
  SignalHelp,
  type SignalTopic,
} from "@/components/ui/signal-help";

/**
 * Inspector's vocabulary. The wording is Inspector's; the popover behaviour is
 * shared with Scout through `ui/signal-help`.
 *
 * Two topics, one per thing a reader has to interpret: what a unit's verdict means,
 * and what the whole-document check covers.
 *
 * There were six, then three, now two. Six because three internal questions each
 * needed explaining plus a presence scale and a severity scale on top. Three because
 * merging the questions merged their explanations, but the result still published a
 * `finding` reason and a unit `status` - one judgement in two vocabularies, which
 * needed two topics to explain the difference between them. There is one axis now,
 * so there is one thing to explain.
 */

export type InspectorSignalTopic = "verdict" | "consistency";

const TOPICS: Record<InspectorSignalTopic, SignalTopic> = {
  verdict: {
    promptRef: { tool: "inspector", stage: "assessment" },
    title: "Verdict",
    summary: "How one rubric unit stands, in one word.",
    detail:
      "Specified and N/A require no follow-up. Other unit verdicts identify a shortfall. Not present and N/A cite no passage; other verdicts cite whole source passages, not exact quotations. There is no overall score or programme-risk rating.",
    // Read from the label maps, not retyped. The vocabulary was a paragraph here and
    // a set of chips on screen, which is two copies of one list and eleven lines a
    // reader has to parse to find the term in front of them.
    terms: VERDICTS.map((verdict) => ({
      term: VERDICT_LABEL[verdict],
      meaning: VERDICT_DESCRIPTION[verdict],
    })),
  },
  consistency: {
    promptRef: { tool: "inspector", stage: "consistency" },
    title: "Cross-section consistency",
    summary: "Do two different sections state claims that cannot both hold?",
    detail:
      "Checked once per document, shared across rubrics. Each conflict cites passages from at least two sections. An incomplete check is reported separately from a completed check with no conflicts.",
  },
};

/** Publication order, read by the documentation panel. */
export const INSPECTOR_TOPIC_LIST: readonly SignalTopic[] = Object.values(TOPICS);

export function InspectorSignalHelp() {
  return (
    <SignalHelp
      title="How to read this assessment"
      intro="Each unit receives one verdict against the selected rubric. Document-wide consistency is a separate check."
      topics={INSPECTOR_TOPIC_LIST as SignalTopic[]}
    />
  );
}
