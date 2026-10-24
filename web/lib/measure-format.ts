/**
 * Numbers with their units, as every tool writes them.
 *
 * Scout's targets and measurements and Drafter's observations print a figure the same way,
 * so the spacing and precision rules live once.
 */

import type { NumericDisplay } from "./api.ts";

/**
 * A number with its unit, spaced.
 *
 * `%` and `°` close up against the number; every other unit takes a space. Shared because
 * two call sites had already diverged - `formatNumericExpression` spaced it and the
 * benchmark formatter did not, which is where `1injections` and `0.6administration
 * occasions` came from.
 */
export function formatMeasure(value: number | null | undefined, unit: string, display?: NumericDisplay): string {
  if (value == null || !Number.isFinite(value)) return "—";
  const formatted = formatMagnitude(value, display);
  if (display?.kind === "calendar_year") return formatted;
  unit = (Math.abs(value) === 1 ? display?.unit_singular : display?.unit_plural) || unit;
  if (!unit) return formatted;
  return /^[%°]/.test(unit) ? `${formatted}${unit}` : `${formatted} ${unit}`;
}

function formatMagnitude(value: number, display?: NumericDisplay): string {
  return value.toLocaleString(undefined, {
    // Keep established two-decimal presentation, without turning a small
    // nonzero measurement into zero.
    ...(value !== 0 && Math.abs(value) < 0.01
      ? { maximumSignificantDigits: 2 }
      : { maximumFractionDigits: 2 }),
    useGrouping: display?.kind !== "calendar_year",
  });
}

/**
 * Two numbers that share a unit, with the unit said once.
 *
 * A range was built by formatting each end on its own, which printed the unit twice:
 * "1 administration occasions-2 administration occasions" for what a reader reads as
 * "1 to 2". The mean and its deviation had the same shape. With a long unit the repetition
 * was most of the cell, and the two numbers, which are the content, were the hardest part
 * to find in it.
 *
 * If either end is missing, both are formatted separately, so the em dash placeholder
 * cannot be read as belonging to the other number's unit.
 */
export function formatMeasurePair(
  first: number | null | undefined,
  second: number | null | undefined,
  unit: string,
  separator: string,
  display?: NumericDisplay,
): string {
  const usable = (value: number | null | undefined) => value != null && Number.isFinite(value);
  if (!usable(first) || !usable(second)) {
    return `${formatMeasure(first, unit, display)}${separator}${formatMeasure(second, unit, display)}`;
  }
  const lead = formatMagnitude(first as number, display);
  return `${lead}${separator}${formatMeasure(second, unit, display)}`;
}
