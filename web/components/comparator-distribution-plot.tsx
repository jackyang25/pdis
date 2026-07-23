import type { Conformity } from "@/lib/api";
import {
  buildComparatorDistribution,
  type DistributionPoint,
} from "@/lib/comparator-distribution";

function formatValue(value: number, unit: string): string {
  const formatted = value.toLocaleString(undefined, { maximumFractionDigits: 3 });
  return unit ? `${formatted}${unit}` : formatted;
}

function tooltipAlignment(x: number): string {
  if (x < 18) return "left-0";
  if (x > 82) return "right-0";
  return "left-1/2 -translate-x-1/2";
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
  const detail = contextual
    ? point.exclusion_reasons.join(" · ")
    : `Identity: ${point.source_identity_status.replaceAll("_", " ")}`;
  return (
    <span
      className="group/point absolute z-10 -translate-x-1/2 outline-none"
      style={{ left: `${point.x}%`, top: `calc(50% + ${laneOffsets[point.lane]}px)` }}
      tabIndex={0}
      role="img"
      aria-label={`${contextual ? "Contextual measurement" : "Included comparator"}: ${formatValue(point.value, unit)}. ${point.source_quote}`}
    >
      <span
        className={contextual
          ? "block h-2.5 w-2.5 -translate-y-1/2 rounded-full border border-muted-foreground bg-card ring-2 ring-card"
          : "block h-2.5 w-2.5 -translate-y-1/2 rounded-full bg-foreground/75 ring-2 ring-card"}
      />
      <span
        className={`pointer-events-none absolute bottom-3 z-30 hidden w-56 rounded-md border border-border bg-popover px-2.5 py-2 text-left shadow-md group-hover/point:block group-focus/point:block ${tooltipAlignment(point.x)}`}
      >
        <span className="block text-[11px] font-semibold text-foreground">
          {formatValue(point.value, unit)} · {contextual ? "Context only" : "Direct comparator"}
        </span>
        <span className="mt-1 block text-[10px] leading-relaxed text-foreground/80">
          “{point.source_quote}”
        </span>
        <span className="mt-1 block truncate text-[10px] text-muted-foreground">
          {point.source_record_id || "Source record"} · {detail}
        </span>
      </span>
    </span>
  );
}

export function ComparatorDistributionPlot({ conformity }: { conformity: Conformity }) {
  const distributionMeasurement = (measurement: Conformity["measurements"][number]) => ({
    value: measurement.expression.value ?? Number.NaN,
    unit: measurement.expression.unit,
    source_quote: measurement.source_quote,
    source_record_id: measurement.source_record_id,
    source_identity_status: measurement.source_identity_status,
    semantic_status: measurement.semantic_status,
    exclusion_reasons: measurement.exclusion_reasons,
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
  const hasIncluded = model.included.length > 0;
  const hasExcluded = model.excluded.length > 0;
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
    <figure className="mt-4 rounded-lg border border-border/70 bg-muted/10 px-4 py-4 sm:px-5">
      <figcaption className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <span className="text-xs font-semibold text-foreground">
          {hasIncluded ? "Comparator distribution" : "Related numeric context"}
        </span>
        <span className="text-[10px] text-muted-foreground">
          {hasIncluded
            ? `${conformity.target_meeting_count}/${conformity.benchmark_count} meet target · ${Math.round(conformity.target_meeting_rate * 100)}% observed share`
            : `${model.excluded.length} contextual measurement${model.excluded.length === 1 ? "" : "s"}`}
        </span>
      </figcaption>

      <div
        className={`relative mt-5 ${hasIncluded && hasExcluded ? "h-[190px]" : "h-[125px]"}`}
        role="group"
        aria-label={`Distribution of ${model.included.length} validated comparators and ${model.excluded.length} contextual measurements. Document target ${target}.`}
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
            Context only
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
              <div
                className="absolute top-[59px] h-2.5 rounded-sm bg-muted-foreground/20"
                style={{ left: `${quartileLeft}%`, width: `${Math.max(quartileWidth, 0.35)}%` }}
                title="Middle 50% of included comparators"
              />
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
        {hasIncluded && <span className="inline-flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-foreground/75" />Direct comparator</span>}
        {hasIncluded && <span className="inline-flex items-center gap-1.5"><span className="h-2 w-5 rounded-sm bg-muted-foreground/20" />Middle 50%</span>}
        <span className="inline-flex items-center gap-1.5"><span className="h-3 border-l border-dashed border-foreground/60" />Document target</span>
        {hasExcluded && <span className="inline-flex items-center gap-1.5"><span className="h-2 w-2 rounded-full border border-muted-foreground bg-card" />Related context, excluded from statistics</span>}
      </div>
      {model.unplottableExcludedCount > 0 && (
        <p className="mt-1.5 text-[9px] text-muted-foreground/70">
          {model.unplottableExcludedCount} incompatible or unresolved candidate{model.unplottableExcludedCount === 1 ? " is" : "s are"} retained in the audit ledger and intentionally not plotted.
        </p>
      )}
    </figure>
  );
}
