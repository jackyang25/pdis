export type DistributionMeasurement = {
  value: number;
  unit: string;
  source_quote: string;
  source_record_id: string;
  source_identity_status: string;
  semantic_status: string;
  exclusion_reasons: string[];
};

export type DistributionInput = {
  targetValue: number;
  unit: string;
  minimum: number | null;
  maximum: number | null;
  median: number | null;
  lowerQuartile: number | null;
  upperQuartile: number | null;
  included: DistributionMeasurement[];
  excluded: DistributionMeasurement[];
};

export type DistributionPoint = DistributionMeasurement & {
  x: number;
  lane: number;
};

export type ComparatorDistributionModel = {
  domainMinimum: number;
  domainMaximum: number;
  targetX: number;
  minimumX: number;
  maximumX: number;
  medianX: number;
  lowerQuartileX: number;
  upperQuartileX: number;
  included: DistributionPoint[];
  excluded: DistributionPoint[];
  unplottableExcludedCount: number;
};

const LANE_COUNT = 7;

function finite(value: number | null): value is number {
  return value != null && Number.isFinite(value);
}

function normalizedUnit(value: string): string {
  return value.trim().toLocaleLowerCase();
}

function clamp(value: number): number {
  return Math.max(0, Math.min(100, value));
}

function position(value: number, minimum: number, maximum: number): number {
  return clamp(((value - minimum) / (maximum - minimum)) * 100);
}

function placePoints(
  measurements: DistributionMeasurement[],
  minimum: number,
  maximum: number,
): DistributionPoint[] {
  const occupiedBins = new Map<number, number>();
  return measurements
    .filter((measurement) => Number.isFinite(measurement.value))
    .map((measurement) => {
      const x = position(measurement.value, minimum, maximum);
      const bin = Math.round(x * 2);
      const count = occupiedBins.get(bin) ?? 0;
      occupiedBins.set(bin, count + 1);
      return { ...measurement, x, lane: count % LANE_COUNT };
    });
}

export function buildComparatorDistribution(
  input: DistributionInput,
): ComparatorDistributionModel | null {
  const included = input.included.filter((measurement) =>
    Number.isFinite(measurement.value),
  );
  // Plot only semantically related context. Incompatible/unknown values remain
  // auditable in the ledger but must not distort the comparison scale.
  const compatibleExcluded = input.excluded.filter(
    (measurement) =>
      Number.isFinite(measurement.value) &&
      measurement.semantic_status === "contextual" &&
      normalizedUnit(measurement.unit) === normalizedUnit(input.unit),
  );
  if (
    (!included.length && !compatibleExcluded.length) ||
    !Number.isFinite(input.targetValue)
  ) return null;
  const domainValues = [
    input.targetValue,
    ...included.map((measurement) => measurement.value),
    ...compatibleExcluded.map((measurement) => measurement.value),
  ];
  let observedMinimum = Math.min(...domainValues);
  let observedMaximum = Math.max(...domainValues);
  const span = observedMaximum - observedMinimum;
  const padding = span > 0
    ? span * 0.08
    : Math.max(Math.abs(observedMinimum) * 0.08, 1);
  observedMinimum -= padding;
  observedMaximum += padding;

  const minimum = finite(input.minimum)
    ? input.minimum
    : included.length
      ? Math.min(...included.map((measurement) => measurement.value))
      : input.targetValue;
  const maximum = finite(input.maximum)
    ? input.maximum
    : included.length
      ? Math.max(...included.map((measurement) => measurement.value))
      : input.targetValue;
  const median = finite(input.median) ? input.median : minimum;
  const lowerQuartile = finite(input.lowerQuartile) ? input.lowerQuartile : median;
  const upperQuartile = finite(input.upperQuartile) ? input.upperQuartile : median;

  return {
    domainMinimum: observedMinimum,
    domainMaximum: observedMaximum,
    targetX: position(input.targetValue, observedMinimum, observedMaximum),
    minimumX: position(minimum, observedMinimum, observedMaximum),
    maximumX: position(maximum, observedMinimum, observedMaximum),
    medianX: position(median, observedMinimum, observedMaximum),
    lowerQuartileX: position(lowerQuartile, observedMinimum, observedMaximum),
    upperQuartileX: position(upperQuartile, observedMinimum, observedMaximum),
    included: placePoints(included, observedMinimum, observedMaximum),
    excluded: placePoints(compatibleExcluded, observedMinimum, observedMaximum),
    unplottableExcludedCount: input.excluded.length - compatibleExcluded.length,
  };
}
