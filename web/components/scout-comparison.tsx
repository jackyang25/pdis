"use client";
import type { Measurement, QuantitativeTarget, QuantitativeSemanticProfile } from "@/lib/api";
import { Reading, Quoted, InterfaceNote } from "@/components/ui/evidence-text";
import { DocumentSourceTrace } from "@/components/document-source-trace";
import { EYEBROW } from "@/lib/typography";
import { cn } from "@/lib/utils";
import { semanticSlotLabel, dimensionLabel, comparisonRuleLabel, comparisonDimensions } from "@/lib/scout-comparison";

export function TargetQualifierSource({ target, dimension }: {
  target?: QuantitativeTarget | null;
  dimension: keyof QuantitativeSemanticProfile;
}) {
  const spans = target?.semantic_provenance[dimension] ?? [];
  if (spans.length === 0) return null;
  return <DocumentSourceTrace spans={spans} blockIds={[...new Set(spans.flatMap(span => span.block_ids))]} />;
}

/** Keep extracted document content separate from the authored matching rule. */
export function TargetQualifierDetails({ target, dimension }: {
  target?: QuantitativeTarget | null;
  dimension: keyof QuantitativeSemanticProfile;
}) {
  return <div className="space-y-2 text-xs leading-relaxed">
    <div>
      <p className="text-[11px] font-medium text-muted-foreground">Document says</p>
      <p className="text-foreground">{semanticSlotLabel(target?.semantic_profile[dimension])}</p>
    </div>
    <TargetComparisonRule target={target} dimension={dimension} />
  </div>;
}

function TargetComparisonRule({ target, dimension }: {
  target?: QuantitativeTarget | null;
  dimension: keyof QuantitativeSemanticProfile;
}) {
  const rule = target?.comparison_contract[dimension];
  const requiresMatch = rule?.mode === "exact" || rule?.mode === "compatible";
  return <div className="text-[11px] leading-relaxed text-muted-foreground">
      <p className="font-medium">{requiresMatch ? "Evidence must match" : "Evidence matching rule"}</p>
      <p>{comparisonRuleLabel(rule)}</p>
      {rule?.reason && rule.mode !== "unknown" && <Reading className="mt-1">{rule.reason}</Reading>}
  </div>;
}

/** Future evidence rules are secondary to checking the extracted document target. */
export function TargetComparisonRules({ target }: { target: QuantitativeTarget }) {
  const dimensions = Object.keys(target.comparison_contract) as Array<keyof QuantitativeSemanticProfile>;
  return <details key={target.id} className="mt-5 rounded-lg border border-border/60">
    <summary className="cursor-pointer rounded-lg px-4 py-3 text-xs font-medium text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">How evidence will be compared</summary>
    <div className="space-y-4 px-4 pb-4">
      <p className="text-xs leading-relaxed text-muted-foreground">Scout will use these rules to decide which external measurements can be compared with this target. Comparable measurements may fall above or below the target value.</p>
      {dimensions.map(dimension => <div key={dimension} className="space-y-1">
        <p className={EYEBROW}>{dimensionLabel(dimension)}</p>
        <TargetComparisonRule target={target} dimension={dimension} />
      </div>)}
    </div>
  </details>;
}

/** Read-only provenance, shared by review and final measurement details. */
export function ScoutComparison({ target, measurement, compact = false }: {
  target?: QuantitativeTarget | null;
  measurement: Measurement;
  compact?: boolean;
}) {
  const dimensions = target ? comparisonDimensions(target)
    : Object.keys(measurement.semantic_assessment.dimensions) as Array<keyof QuantitativeSemanticProfile>;
  const unconstrained = target
    ? (Object.keys(target.comparison_contract) as Array<keyof QuantitativeSemanticProfile>)
      .filter(dimension => target.comparison_contract[dimension].mode === "unconstrained") : [];
  const ownership = measurement.semantic_assessment.source_ownership;
  return <div className="space-y-3">
    {measurement.source_passage && measurement.source_passage !== measurement.source_quote && <details className="rounded-lg border border-border/60">
      <summary className="cursor-pointer rounded-lg px-4 py-3 text-xs font-medium text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">Retained source context</summary>
      <div className="px-4 pb-4"><Quoted>{measurement.source_passage}</Quoted></div>
    </details>}
    <div className="mt-3 text-xs leading-relaxed text-muted-foreground">
      <p className="font-medium">Source ownership: {ownership.state === "yes" ? "Attributed to this source" : ownership.state === "no" ? "Not attributed to this source" : "Uncertain"}</p>
      {ownership.reason ? <Reading>{ownership.reason}</Reading> : <p>No source-ownership explanation was recorded.</p>}
    </div>
    {dimensions.length > 0 && <ReviewComparisonTable target={target ?? undefined} measurement={measurement} dimensions={dimensions} compact={compact} />}
    {unconstrained.length > 0 && <details key={measurement.candidate_id} className="rounded-lg border border-border/60">
      <summary className="cursor-pointer rounded-lg px-4 py-3 text-xs font-medium text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
        Fields that do not control comparison
      </summary>
      <div className="px-4 pb-4">
        <p className="text-xs leading-relaxed text-muted-foreground">These fields are not required to match. Their inclusion here does not establish that they are equivalent.</p>
        <ReviewComparisonTable target={target ?? undefined} measurement={measurement} dimensions={unconstrained} compact={compact} />
      </div>
    </details>}
    {compact && measurement.ai_review_reason && <div className="border-t border-border/60 pt-3 text-xs">
      <p className="font-medium">{measurement.ai_recommendation === "unavailable" ? "Independent AI review unavailable" : "Independent AI recommendation"}</p>
      {measurement.ai_recommendation === "unavailable" ? <InterfaceNote>{measurement.ai_review_reason}</InterfaceNote> : <Reading>{measurement.ai_review_reason}</Reading>}
    </div>}
  </div>;
}

/** Display the mapper's authored fields without merging them with the reviewer's advice. */
function ReviewComparisonTable({ target, measurement, dimensions, compact }: {
  target: QuantitativeTarget | undefined;
  measurement: Measurement;
  dimensions: Array<keyof QuantitativeSemanticProfile>;
  compact: boolean;
}) {
  return <div className="mt-3 overflow-hidden rounded-lg border border-border/60">
    <div className={cn(EYEBROW, "hidden grid-cols-[0.7fr_1fr_1fr_1.3fr] gap-4 bg-foreground/[0.045] px-4 py-2", !compact && "sm:grid")}>
      <span>Dimension</span><span>Target</span><span>Evidence</span><span>Mapping and explanation</span>
    </div>
    {dimensions.map(dimension => {
      const rule = target?.comparison_contract[dimension];
      const mapped = measurement.semantic_assessment.dimensions[dimension];
      const state = mapped?.compatibility.state ?? "unknown";
      const unconstrained = rule?.mode === "unconstrained";
      const spans = target?.semantic_provenance[dimension] ?? [];
      return <div key={dimension} className={cn("grid gap-3 border-t border-border/60 px-4 py-3 first:border-t-0", !compact && "sm:grid-cols-[0.7fr_1fr_1fr_1.3fr] sm:gap-4")}>
        <p className="text-xs font-medium text-foreground">{dimensionLabel(dimension)}</p>
        <div className="min-w-0 break-words text-xs leading-relaxed text-foreground">
          <p className={cn(EYEBROW, "mb-1", !compact && "sm:hidden")}>Target</p>
          <TargetQualifierDetails target={target} dimension={dimension} />
          {spans.length > 0 && <div className="mt-2"><TargetQualifierSource target={target} dimension={dimension} /></div>}
        </div>
        <div className="min-w-0 break-words text-xs leading-relaxed text-foreground">
          <p className={cn(EYEBROW, "mb-1", !compact && "sm:hidden")}>Evidence</p>
          <p>{semanticSlotLabel(mapped?.source)}</p>
        </div>
        <div className="min-w-0 break-words text-xs leading-relaxed text-muted-foreground">
          <p className={cn(EYEBROW, "mb-1", !compact && "sm:hidden")}>Mapping and explanation</p>
          <p className="font-medium">{unconstrained ? "Does not control comparison" : state === "yes" ? "Aligned" : state === "no" ? "Different" : "Uncertain"}</p>
          {mapped?.compatibility.reason
            ? <Reading className="mt-2">{mapped.compatibility.reason}</Reading>
            : <p className="mt-2 text-[11px]">No field-level explanation was recorded.</p>}
        </div>
      </div>;
    })}
  </div>;
}
