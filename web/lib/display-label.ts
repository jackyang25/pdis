/**
 * The one acronym set for user-facing labels. `scout-labels.ts` imports this so
 * a field ref and a config key never disagree about the same word.
 */
export const ACRONYMS = new Set([
  // Organizations and document types
  "who",
  "bmgf",
  "fda",
  "tpp",
  "ipdp",
  "ppc",
  // Indications and pathogens
  "hiv",
  "tb",
  "rsv",
  "hpv",
  "cmv",
  "covid19",
  // Study and quality vocabulary
  "gcp",
  "glp",
  "gmp",
  "poc",
  "rct",
]);

const SPECIAL_LABELS: Record<string, string> = {
  itpp: "iTPP",
  ctpp: "cTPP",
};

/** Canonical presentation for internal enum/config keys. Storage remains
 * lowercase and stable; all user-facing selectors share this formatter. */
export function displayLabel(value: string): string {
  const lower = value.toLowerCase();
  if (SPECIAL_LABELS[lower]) return SPECIAL_LABELS[lower];
  if (ACRONYMS.has(lower)) return lower.toUpperCase();
  return value
    .split("_")
    .map((word) => (word ? word[0].toUpperCase() + word.slice(1) : ""))
    .join(" ");
}
