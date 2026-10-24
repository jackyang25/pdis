/**
 * When a source says it was published, to the month: "Mar 2024".
 *
 * Null when the source stated no date or one that does not parse, so a caller says so in
 * its own words. Two copies of this disagreed: one read an unparseable date as
 * "Invalid Date" beside the source it described.
 */
export function formatPublishedMonth(
  iso: string | null | undefined,
  /** How much of the date the source stated. A year-only date is held as 1 January, and
   *  shown to the month it read as a January publication it never claimed. */
  precision?: "day" | "month" | "year" | "",
): string | null {
  if (!iso) return null;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  if (precision === "year") return String(date.getUTCFullYear());
  return date.toLocaleDateString("en-US", { year: "numeric", month: "short", timeZone: "UTC" });
}

/**
 * Day precision, unlike `formatPublishedMonth` - a window boundary is a specific day, and
 * rendering it to the month would misstate which evidence was admitted. Parsed as
 * local midnight so a UTC-negative timezone does not display the day before.
 */
export function formatWindowDate(iso: string | undefined): string | null {
  if (!iso) return null;
  const d = new Date(`${iso}T00:00:00`);
  if (isNaN(d.getTime())) return null;
  return d.toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}
