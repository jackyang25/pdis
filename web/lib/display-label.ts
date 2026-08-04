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
  "gbs",
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

/** One word of a key, resolved against the shared vocabularies. */
function labelWord(word: string): string {
  if (!word) return "";
  const lower = word.toLowerCase();
  if (SPECIAL_LABELS[lower]) return SPECIAL_LABELS[lower];
  if (ACRONYMS.has(lower)) return lower.toUpperCase();
  return word[0].toUpperCase() + word.slice(1);
}

/** Canonical presentation for internal enum/config keys. Storage remains
 * lowercase and stable; all user-facing selectors share this formatter.
 *
 * Acronyms resolve per word, not only for a whole key: a compound tag such as
 * `gbs_neonatal_sepsis` otherwise renders "Gbs". `scout-labels.ts` already
 * reads the set per word, and the two disagreeing about the same word is what
 * sharing the set is meant to prevent. */
export function displayLabel(value: string): string {
  return value.split("_").map(labelWord).join(" ");
}
