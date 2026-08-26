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
      "One question per unit and one answer, so a count of anything but Specified is a count of things to do. Every verdict except an absence cites the exact passage it was read from. Nothing here says what a shortfall costs your programme, because that is not something this tool can see: there is no letter grade, no severity scale, and no overall score.",
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
      "Only conflicts spanning more than one section are reported here, and a conflict must cite passages from at least two of them; that span is what makes it cross-section. A problem inside one section belongs to that unit instead. This check compares your document with itself and never consults outside evidence. If it does not complete, that is reported as its own status rather than as a document with nothing wrong.",
  },
};

/** Publication order, read by the documentation panel. */
export const INSPECTOR_TOPIC_LIST: readonly SignalTopic[] = Object.values(TOPICS);

export function InspectorSignalHelp() {
  return (
    <SignalHelp
      title="How to read this assessment"
      intro="Inspector checks one document against its authored rubric. Every unit the rubric asks about gets one verdict, and every verdict cites the passage it came from."
      topics={INSPECTOR_TOPIC_LIST as SignalTopic[]}
    />
  );
}
