import type { EvidenceAssessment, PrecedentSignal } from "@/lib/api";
import { GROUNDING_LABEL, GROUNDING_TONE, OUTCOME_LABEL, OUTCOME_TONE, PRECEDENT_LABEL, RELATIONSHIP_LABEL, RELATIONSHIP_TONE } from "@/lib/scout-labels";
import { SignalChip } from "@/components/ui/signal-chip";
import { ResultSummary } from "@/components/ui/result-summary";

type Props = {
  relations: { contradicts: number; confirms: number };
  strength: EvidenceAssessment["strength"] | null;
  precedent: Pick<PrecedentSignal, "precedent" | "outcome"> | null;
  targetCount: number;
  comparatorCount: number;
  insightCount: number;
};

/** Scout owns the meaning and visibility of its independent summary axes. */
export function ScoutFieldSummary({ relations, strength, precedent, targetCount, comparatorCount, insightCount }: Props) {
  return (
    <ResultSummary
      signals={[
        relations.contradicts > 0 && <SignalChip key="conflicts" tone={RELATIONSHIP_TONE.contradicts}>{`${RELATIONSHIP_LABEL.contradicts} ${relations.contradicts}`}</SignalChip>,
        relations.confirms > 0 && <SignalChip key="supports" tone={RELATIONSHIP_TONE.confirms}>{`${RELATIONSHIP_LABEL.confirms} ${relations.confirms}`}</SignalChip>,
        strength && <SignalChip key="grounding" tone={GROUNDING_TONE[strength]}>{GROUNDING_LABEL[strength]}</SignalChip>,
      ]}
      details={[
        precedent && (
          <span key="precedent" role="group" aria-label="Precedent assessment" className="inline-flex flex-wrap items-center gap-x-3 gap-y-1.5">
            <SignalChip tone="neutral" className="font-normal text-muted-foreground">{PRECEDENT_LABEL[precedent.precedent]}</SignalChip>
            <SignalChip tone={OUTCOME_TONE[precedent.outcome]} className="font-normal text-muted-foreground">{OUTCOME_LABEL[precedent.outcome]}</SignalChip>
          </span>
        ),
        <span key="counts" role="group" aria-label="Inventory counts" className="inline-flex flex-wrap items-center gap-x-4 gap-y-1.5">
          {targetCount > 0 && <span>Numeric targets <span className="tabular-nums">{targetCount}</span></span>}
          {targetCount > 0 && comparatorCount > 0 && <span>Comparators <span className="tabular-nums">{comparatorCount}</span></span>}
          <span>Insights <span className="tabular-nums">{insightCount}</span></span>
        </span>,
      ]}
    />
  );
}
