/**
 * One presentation vocabulary for Scout result data.
 *
 * The evidence map and the document trace both render field refs, relationship
 * labels, and source lanes. They previously each owned a copy, and the copies had
 * already drifted — one replaced only underscores, the other also replaced dots
 * and hyphens, so one ref rendered two ways in two views of the same run. Every
 * view now imports from here.
 *
 * Enum and config keys (org, document type, intervention class) are a separate
 * concern owned by `display-label.ts`; both share its acronym set.
 */

// Relative specifiers keep their `.ts` extension: `node --test` resolves value
// imports at runtime, so an extensionless path fails there even though tsc
// accepts it. Type-only imports are erased and would work either way.
import type { EvidenceAssessment, Match, PrecedentSignal } from "./api.ts";
import { ACRONYMS } from "./display-label.ts";

export const RELATIONSHIP_LABEL: Record<Match["relation"], string> = {
  contradicts: "Conflicts",
  extends: "Adds context",
  confirms: "Supports",
  unrelated: "Unrelated",
};

export const GROUNDING_LABEL: Record<EvidenceAssessment["strength"], string> = {
  well_grounded: "Well grounded",
  partial: "Partial",
  thin: "Thin",
  unsupported: "Unsupported",
  unknown: "Unknown",
};

export const PRECEDENT_LABEL: Record<PrecedentSignal["precedent"], string> = {
  direct: "Direct",
  adjacent: "Adjacent",
  none: "None found",
  unknown: "Unknown",
};

export const OUTCOME_LABEL: Record<PrecedentSignal["outcome"], string> = {
  favorable: "Favorable",
  mixed: "Mixed",
  unfavorable: "Unfavorable",
  unknown: "Unknown",
};

/** Present one field ref, dropping its namespace and titling each word. */
export function displayAttributeLabel(ref: string): string {
  const local = ref.includes(".") ? ref.split(".").slice(1).join(".") : ref;
  return local
    .replace(/[._-]+/g, " ")
    .split(" ")
    .filter(Boolean)
    .map((word) =>
      ACRONYMS.has(word.toLowerCase())
        ? word.toUpperCase()
        : word.charAt(0).toUpperCase() + word.slice(1).toLowerCase(),
    )
    .join(" ");
}

/** Prefer the lane label a source adapter supplied over a derived one. */
export function sourceDisplayLabel(
  source: string,
  labels?: Record<string, string>,
): string {
  return (
    labels?.[source] ??
    source
      .replace(/[_-]+/g, " ")
      .replace(/\b\w/g, (character) => character.toUpperCase())
  );
}
