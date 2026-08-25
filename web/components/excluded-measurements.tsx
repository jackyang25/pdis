"use client";

import { useState } from "react";
import { FilterX } from "lucide-react";
import { TracePanelHeader, TracePanelSection } from "@/components/document-trace-panel";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { ProvenanceTrigger, stopRowToggle } from "@/components/ui/provenance";
import { Computed, Reading, SourceEntry } from "@/components/ui/evidence-text";
import type { Conformity, Match, Measurement } from "@/lib/api";
import { SEMANTIC_STATUS_LABEL } from "@/lib/scout-labels";
import { formatMeasure } from "@/lib/scout-result-view";

/**
 * What one numeric target's comparison left out, and why.
 *
 * The third direction of provenance, and the largest by far: across twelve targets on a
 * real run there were 4 admitted measurements against 60 excluded ones and 293 source
 * passage dispositions. The audit trail dwarfs the result, which is exactly why it belongs
 * behind a trigger rather than in two inline disclosures competing with the target above.
 *
 * One trigger, one idiom. `In document` points inward at the uploaded file, `Sources` points
 * outward at findings, and this points at the comparison itself. All three are the same
 * shape of button opening the same shape of panel, so a reader learns the affordance once.
 *
 * Two sections inside, because they are two different failures and merging them would hide
 * that: a measurement that was read and rejected is not the same as a passage the run could
 * not read at all.
 */
export function ExcludedMeasurements({
  conformity,
  matches,
}: {
  conformity: Conformity;
  /** Supplies each measurement's paper title. Without it this panel named sources by DOI
   *  while the cohort beside it named the same papers by title. */
  matches: Match[];
}) {
  const [open, setOpen] = useState(false);
  const excluded = conformity.excluded_measurements ?? [];
  // Only the dispositions that represent something unfinished. `no_relevant_measurement`
  // is the ordinary outcome - the passage simply held no number for this target - and
  // listing 47 of those would bury the one the run could not read.
  const unresolved = (conformity.source_dispositions ?? []).filter(
    (item) => item.status === "not_assessed" || item.status === "uncertain",
  );
  const total = excluded.length + unresolved.length;
  if (total === 0) return null;
  const reviewed = conformity.source_dispositions?.length ?? 0;
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button type="button" {...stopRowToggle}>
          <ProvenanceTrigger
            icon={FilterX}
            label="Excluded"
            count={total}
            ariaLabel={`Excluded: ${total} measurement${total === 1 ? "" : "s"} or passage${total === 1 ? "" : "s"} that did not enter this comparison`}
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
          eyebrow="Excluded"
          title="What this comparison left out"
          description={`${reviewed} source passage${reviewed === 1 ? "" : "s"} were reviewed for this target. These are the ones that did not enter the cohort.`}
        />
        <div className="max-h-[min(60vh,520px)] space-y-4 overflow-y-auto px-4 py-4">
          {excluded.length > 0 && (
            <TracePanelSection label="Read, then not admitted" className="border-t-0 pt-0">
              <ul className="mt-1.5 space-y-3">
                {excluded.map((measurement, index) => (
                  <ExcludedMeasurement
                    key={`${measurement.url}-${index}`}
                    measurement={measurement}
                    unit={conformity.unit}
                    title={titleFor(measurement, matches)}
                  />
                ))}
              </ul>
            </TracePanelSection>
          )}
          {unresolved.length > 0 && (
            <TracePanelSection label="Could not be read" icon={FilterX}>
              <ul className="mt-1.5 space-y-2">
                {unresolved.map((item) => (
                  <SourceEntry
                    key={item.source_id}
                    title={dispositionTitle(item, matches) || item.url}
                    href={item.url}
                    reading={item.reason}
                  />
                ))}
              </ul>
            </TracePanelSection>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}

function dispositionTitle(
  disposition: Conformity["source_dispositions"][number],
  matches: Match[],
): string {
  return (
    matches
      .find((match) => match.insight.id === disposition.insight_id)
      ?.insight.supporting_findings.find((finding) => finding.url === disposition.url)
      ?.title ?? ""
  );
}

function titleFor(measurement: Measurement, matches: Match[]): string {
  return (
    matches
      .find((match) => match.insight.id === measurement.insight_id)
      ?.insight.supporting_findings.find((finding) => finding.url === measurement.url)
      ?.title ?? ""
  );
}

function ExcludedMeasurement({
  measurement,
  unit,
  title,
}: {
  measurement: Measurement;
  unit: string;
  title: string;
}) {
  const value = measurement.expression?.value;

  // Why it was left out, split by who established it. A structural check is a fact about the
  // source's own numbers and cannot be wrong; the semantic reason beside it is a model's
  // reading and can be. Joined with a middot they were one paragraph, and the facts were
  // rendered in the muted tone that means "a model wrote this".
  const structural = measurement.structural_reasons ?? [];
  const judgment =
    measurement.semantic_status !== "comparable" ? measurement.semantic_reason || "" : "";
  // Whatever neither field claims: a reviewer's own words, or the tool's needs-review
  // sentence. On a result saved before `structural_reasons` existed this also holds the
  // checks, which then read as they did before rather than being lost. Filtering by exact
  // equality also drops the second copy those older results carry.
  const remaining = (measurement.exclusion_reasons ?? []).filter(
    (reason) => reason !== judgment && !structural.includes(reason),
  );

  return (
    <SourceEntry
      title={title || measurement.source_record_id || measurement.url}
      href={measurement.url}
      meta={`${
        value != null
          ? formatMeasure(value, measurement.expression?.unit || unit)
          : "no single value"
      } · ${SEMANTIC_STATUS_LABEL[measurement.semantic_status]}`}
      quote={measurement.source_quote}
      reading={judgment || undefined}
    >
      {structural.length > 0 && (
        <ul className="mt-1 space-y-0.5">
          {structural.map((reason) => (
            <li key={reason}>
              <Computed className="text-[11px] leading-relaxed">{reason}</Computed>
            </li>
          ))}
        </ul>
      )}
      {remaining.length > 0 && <Reading>{remaining.join(" · ")}</Reading>}
    </SourceEntry>
  );
}
