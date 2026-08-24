"use client";

import { useState } from "react";
import { ChevronDown, Scale } from "lucide-react";
import { TracePanelHeader } from "@/components/document-trace-panel";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { ProvenanceTrigger, stopRowToggle } from "@/components/ui/provenance";
import { Reading, SourceEntry } from "@/components/ui/evidence-text";
import type { Conformity, Insight, Match, Measurement } from "@/lib/api";
import { SEMANTIC_STATUS_LABEL, sourceIdentityCaveat } from "@/lib/scout-labels";
import { calibrationView, formatMeasure } from "@/lib/scout-result-view";

/**
 * The measurements a target's statistics were computed from.
 *
 * Behind a trigger, like `Excluded` beside it. Asymmetry was the reason: what a comparison
 * left out sat behind a click while what it admitted ran inline for five lines per
 * measurement, so two halves of one audit had two different affordances. The statistics and
 * the plot above already say what this cohort amounts to; this is the detail behind them,
 * which is the same tier as what was rejected.
 *
 * Each entry uses the shared `SourceEntry` shape. It previously stacked five origins with
 * nothing to tell them apart: the paper's title, its exact words, a sentence the backend
 * wrote about deduplication, a disclosure, and a model's reading of the paper. The backend
 * sentence is gone; it described the pipeline, not the evidence.
 */
export function ComparatorCohort({
  conformity,
  matches,
}: {
  conformity: Conformity;
  matches: Match[];
}) {
  const [open, setOpen] = useState(false);
  const admitted = conformity.measurements ?? [];
  if (admitted.length === 0) return null;
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button type="button" {...stopRowToggle}>
          <ProvenanceTrigger
            icon={Scale}
            label="Comparators"
            count={admitted.length}
            ariaLabel={`Comparators: the ${admitted.length} measurement${admitted.length === 1 ? "" : "s"} this target's statistics were computed from`}
          />
        </button>
      </PopoverTrigger>
      <PopoverContent
        align="start"
        sideOffset={6}
        collisionPadding={12}
        className="w-[min(720px,calc(100vw-24px))] overflow-hidden p-0"
      >
        <TracePanelHeader
          eyebrow="Comparators"
          title="What the statistics were computed from"
          // The phrase comes from `calibrationView`, which is tested, rather than being
          // built here from the same two fields. Two constructions of one sentence is how
          // "3 of 3" and "3 of 3 meet target" come to disagree about the wording.
          description={`Every measurement admitted for this target. ${calibrationView(conformity).meetingLabel}.`}
        />
        <div className="max-h-[min(60vh,520px)] overflow-y-auto px-4 py-4">
          <ul>
            {admitted.map((measurement, index) => (
              <AdmittedMeasurement
                key={`${measurement.url}-${index}`}
                measurement={measurement}
                unit={conformity.unit}
                insight={insightFor(measurement, matches)}
              />
            ))}
          </ul>
        </div>
      </PopoverContent>
    </Popover>
  );
}

function insightFor(measurement: Measurement, matches: Match[]): Insight | undefined {
  return matches.find((match) => match.insight.id === measurement.insight_id)?.insight;
}

function AdmittedMeasurement({
  measurement,
  unit,
  insight,
}: {
  measurement: Measurement;
  unit: string;
  insight?: Insight;
}) {
  const [open, setOpen] = useState(false);
  const finding = insight?.supporting_findings.find(
    (candidate) => candidate.url === measurement.url,
  );
  const value = measurement.expression?.value;
  const age =
    measurement.age_months != null
      ? `${Math.round(measurement.age_months)} months old`
      : "date not stated";
  // `inclusion_reason` was one identical sentence on every admitted measurement
  // ("Manually selected; typed calculation inputs and evidence-unit deduplication were
  // retained"), which describes the pipeline rather than the evidence and discriminates
  // nothing. What it was really carrying is here instead, and only when it is the exception:
  // a measurement that entered without review is the one worth checking.
  const unreviewed =
    measurement.admission_status !== "approved"
      ? `Entered without review (${measurement.admission_status.replaceAll("_", " ")})`
      : "";
  // Shown here as well as on the plot. It was on the plot alone, so a reader auditing the
  // cohort through this panel never learned that a source had no canonical identifier, even
  // though that is what caps the comparator basis at "Limited".
  const identity = sourceIdentityCaveat(measurement.source_identity_status);
  return (
    <SourceEntry
      title={finding?.title || measurement.source_record_id || "Cited source"}
      href={measurement.url}
      meta={`${value != null ? formatMeasure(value, measurement.expression?.unit || unit) : "no single value"} · ${age}`}
      quote={measurement.source_quote}
      reading={insight?.statement}
    >
      {unreviewed && <Reading>{unreviewed}</Reading>}
      {identity && <Reading>{identity}</Reading>}
      {/* The semantic match is a model's reading too, but per axis and long, so it stays
          collapsed rather than being a fourth line on every entry. */}
      <details className="group/semantic mt-1" open={open} onToggle={(event) => setOpen((event.target as HTMLDetailsElement).open)}>
        <summary className="inline-flex cursor-pointer select-none items-center gap-1 text-[11px] text-muted-foreground outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/20 [&::-webkit-details-marker]:hidden">
          Why it was comparable
          <ChevronDown className="h-2.5 w-2.5 transition-transform group-open/semantic:rotate-180 motion-reduce:transition-none" />
        </summary>
        <Reading className="pl-3">
          {SEMANTIC_STATUS_LABEL[measurement.semantic_status]}
          {measurement.semantic_reason ? `. ${measurement.semantic_reason}` : ""}
        </Reading>
      </details>
    </SourceEntry>
  );
}
