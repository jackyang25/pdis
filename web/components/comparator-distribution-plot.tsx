import type { Conformity, Match } from "@/lib/api";
import {
  buildComparatorDistribution,
  type DistributionPoint,
} from "@/lib/comparator-distribution";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { InterfaceNote, Quoted, Reading } from "@/components/ui/evidence-text";
import { sourceIdentityCaveat } from "@/lib/scout-labels";
import { formatMeasure } from "@/lib/scout-result-view";

// The shared formatter, not a local copy: this one had the same missing space as the
// benchmark formatter, which is how "0.6administration occasions" reached an axis label.
const formatValue = formatMeasure;

function popoverAlignment(x: number): "start" | "center" | "end" {
  if (x < 18) return "start";
  if (x > 82) return "end";
  return "center";
}

function Point({
  point,
  unit,
  contextual = false,
}: {
  point: DistributionPoint;
  unit: string;
  contextual?: boolean;
}) {
  const laneOffsets = [-9, 0, 9, -18, 18, -27, 27];
  // Only on an admitted point. How a source was identified never decides whether a
  // measurement is admitted - that is its semantic status and the structural checks - so on a
  // point already outside the cohort it is a caveat about nothing. On an admitted one it is
  // load-bearing: a cohort cannot report a verified basis unless every source is canonical.
  const identity = contextual ? "" : sourceIdentityCaveat(point.source_identity_status);
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          className="absolute z-10 flex h-5 w-5 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full outline-none transition-colors hover:bg-foreground/[0.045] focus-visible:ring-2 focus-visible:ring-ring/30 motion-reduce:transition-none"
          style={{ left: `${point.x}%`, top: `calc(50% + ${laneOffsets[point.lane]}px)` }}
          aria-label={`${contextual ? "Non-admitted measurement" : "Admitted comparator"}: ${formatValue(point.value, unit)}. ${point.source_quote}`}
        >
          <span
            className={contextual
              ? "block h-2.5 w-2.5 rounded-full border border-muted-foreground bg-card ring-2 ring-card"
              : "block h-2.5 w-2.5 rounded-full bg-foreground/75 ring-2 ring-card"}
          />
        </button>
      </PopoverTrigger>
      <PopoverContent
        side="top"
        align={popoverAlignment(point.x)}
        sideOffset={6}
        className="w-[min(300px,calc(100vw-32px))] p-3"
      >
        <p className="text-xs font-semibold text-foreground">
          {formatValue(point.value, unit)} · {contextual ? "Not admitted" : "Admitted comparator"}
        </p>
        <Quoted className="mt-2">{point.source_quote}</Quoted>
        {/* Title then detail, in the order and the tones `SourceEntry` uses. This card
            showed the same source muted while the cohort list beside it showed it at full
            contrast, so one measurement looked like two kinds of thing. */}
        <p className="mt-2 break-words text-[11px] font-medium text-foreground">
          {point.title || point.source_record_id || "Cited source"}
        </p>
        {identity && <Reading>{identity}</Reading>}
      </PopoverContent>
    </Popover>
  );
}

export function ComparatorDistributionPlot({
  conformity,
  matches,
}: {
  conformity: Conformity;
  /** Supplies each measurement's paper title, so a dot identifies itself the way the
   *  cohort and the excluded panel do rather than by DOI. */
  matches: Match[];
}) {
  const titleFor = (measurement: Conformity["measurements"][number]) =>
    matches
      .find((match) => match.insight.id === measurement.insight_id)
      ?.insight.supporting_findings.find((finding) => finding.url === measurement.url)
      ?.title ?? "";
  const distributionMeasurement = (measurement: Conformity["measurements"][number]) => ({
    value: measurement.expression.value ?? Number.NaN,
    title: titleFor(measurement),
    unit: measurement.expression.unit,
    expressionKind: measurement.expression.kind,
    source_quote: measurement.source_quote,
    source_record_id: measurement.source_record_id,
    source_identity_status: measurement.source_identity_status,
    semantic_status: measurement.semantic_status,
  });
  const model = buildComparatorDistribution({
    targetValue: conformity.target_value,
    unit: conformity.unit,
    minimum: conformity.benchmark_minimum,
    maximum: conformity.benchmark_maximum,
    median: conformity.benchmark_median,
    lowerQuartile: conformity.benchmark_lower_quartile,
    upperQuartile: conformity.benchmark_upper_quartile,
    included: conformity.measurements.map(distributionMeasurement),
    excluded: conformity.excluded_measurements.map(distributionMeasurement),
  });
  if (!model) return null;
  // A distribution needs something to distribute. Below two plotted points the mark says
  // less than the number beside it does - a "range" of "1 injections–1 injections" over a
  // single dot, which was 11 of 12 targets on a real run. The values are still shown as
  // text by the caller, and every measurement stays in the ledger below.
  if (model.included.length + model.excluded.length < 2) return null;
  const hasIncluded = model.included.length > 0;
  const hasExcluded = model.excluded.length > 0;
  const showQuartiles = model.included.length >= 4;
  const excludedLabelTop = hasIncluded ? 132 : 68;
  const excludedAxisTop = hasIncluded ? 140 : 74;
  const excludedPointsTop = hasIncluded ? 119 : 53;

  const rangeLeft = Math.min(model.minimumX, model.maximumX);
  const rangeWidth = Math.abs(model.maximumX - model.minimumX);
  const quartileLeft = Math.min(model.lowerQuartileX, model.upperQuartileX);
  const quartileWidth = Math.abs(model.upperQuartileX - model.lowerQuartileX);
  const target = formatValue(conformity.target_value, conformity.unit);
  const targetLabelAlignment = model.targetX < 18
    ? ""
    : model.targetX > 82
      ? "-translate-x-full"
      : "-translate-x-1/2";

  return (
    <figure className="mt-4 rounded-lg border border-border/70 bg-foreground/[0.045] px-4 py-4 sm:px-5">
      <figcaption className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <span className="text-xs font-semibold text-foreground">
          {hasIncluded ? "Comparator distribution" : "Related numeric context"}
        </span>
        <span className="text-[10px] text-muted-foreground">
          {hasIncluded
            ? `${conformity.target_meeting_count}/${conformity.benchmark_count} meet target · ${Math.round(conformity.target_meeting_rate * 100)}% observed share`
            : `${model.excluded.length} non-admitted measurement${model.excluded.length === 1 ? "" : "s"}`}
        </span>
      </figcaption>

      <div
        className={`relative mt-5 ${hasIncluded && hasExcluded ? "h-[190px]" : "h-[125px]"}`}
        role="group"
        aria-label={`Distribution of ${model.included.length} admitted comparators and ${model.excluded.length} non-admitted measurements. Document target ${target}.`}
      >
        {hasIncluded && (
          <span className="absolute left-0 top-[58px] text-[9px] uppercase tracking-wide text-muted-foreground">
            Direct cohort
          </span>
        )}
        {hasExcluded && (
          <span
            className="absolute left-0 text-[9px] uppercase tracking-wide text-muted-foreground"
            style={{ top: `${excludedLabelTop}px` }}
          >
            Not admitted
          </span>
        )}

        <div className="absolute inset-y-0 left-14 right-0">
          {hasIncluded && (
            <>
              <div className="absolute inset-x-0 top-[64px] border-t border-border" />
              <div
                className="absolute top-[63px] h-0.5 bg-muted-foreground/50"
                style={{ left: `${rangeLeft}%`, width: `${rangeWidth}%` }}
              />
              {showQuartiles && (
                <div
                  className="absolute top-[59px] h-2.5 rounded-sm bg-muted-foreground/20"
                  style={{ left: `${quartileLeft}%`, width: `${Math.max(quartileWidth, 0.35)}%` }}
                  title="Middle 50% of included comparators"
                />
              )}
              <div
                className="absolute top-[55px] h-[18px] w-px bg-foreground/55"
                style={{ left: `${model.medianX}%` }}
                title={`Median ${formatValue(conformity.benchmark_median ?? conformity.target_value, conformity.unit)}`}
              />
            </>
          )}

          <div
            className="absolute inset-y-1 z-0 border-l border-dashed border-foreground/60"
            style={{ left: `${model.targetX}%` }}
          />
          <span
            className={`absolute top-0 z-20 whitespace-nowrap rounded bg-card px-1.5 py-0.5 text-[9px] font-medium text-foreground shadow-sm ${targetLabelAlignment}`}
            style={{ left: `${model.targetX}%` }}
          >
            Target · {target}
          </span>

          <div className="absolute inset-x-0 top-[44px] h-10">
            {model.included.map((point, index) => (
              <Point key={`${point.source_record_id}-${point.value}-${index}`} point={point} unit={conformity.unit} />
            ))}
          </div>

          {hasExcluded && (
            <>
              <div
                className="absolute inset-x-0 border-t border-dashed border-border/70"
                style={{ top: `${excludedAxisTop}px` }}
              />
              <div
                className="absolute inset-x-0 h-10"
                style={{ top: `${excludedPointsTop}px` }}
              >
                {model.excluded.map((point, index) => (
                  <Point key={`${point.source_record_id}-${point.value}-context-${index}`} point={point} unit={conformity.unit} contextual />
                ))}
              </div>
            </>
          )}
        </div>
      </div>

      <div className="ml-14 flex justify-between border-t border-border/70 pt-1 text-[9px] tabular-nums text-muted-foreground">
        <span>{formatValue(model.domainMinimum, conformity.unit)}</span>
        <span>{formatValue(model.domainMaximum, conformity.unit)}</span>
      </div>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[9px] text-muted-foreground">
        {hasIncluded && <span className="inline-flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-foreground/75" />Admitted comparator</span>}
        {showQuartiles && <span className="inline-flex items-center gap-1.5"><span className="h-2 w-5 rounded-sm bg-muted-foreground/20" />Middle 50%</span>}
        <span className="inline-flex items-center gap-1.5"><span className="h-3 border-l border-dashed border-foreground/60" />Document target</span>
        {hasExcluded && <span className="inline-flex items-center gap-1.5"><span className="h-2 w-2 rounded-full border border-muted-foreground bg-card" />Candidate or context, not admitted</span>}
      </div>
      {model.unplottableExcludedCount > 0 && (
        <InterfaceNote className="mt-2">
          {model.unplottableExcludedCount} further excluded measurement{model.unplottableExcludedCount === 1 ? "" : "s"} cannot be
          plotted, because {model.unplottableExcludedCount === 1 ? "it states" : "they state"} no single
          comparable number. Excluded lists {model.unplottableExcludedCount === 1 ? "it" : "them"} with the reason.
        </InterfaceNote>
      )}
    </figure>
  );
}
