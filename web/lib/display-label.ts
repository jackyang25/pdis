const ACRONYMS = new Set([
  "who",
  "bmgf",
  "tpp",
  "ipdp",
  "ppc",
  "hiv",
  "tb",
  "rsv",
  "hpv",
  "covid19",
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
