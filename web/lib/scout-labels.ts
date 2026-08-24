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
import type {
  Conformity,
  EvidenceAssessment,
  Match,
  Measurement,
  PrecedentSignal,
  QuantitativeStatementDisposition,
} from "./api.ts";
import { ACRONYMS } from "./display-label.ts";

export const RELATIONSHIP_LABEL: Record<Match["relation"], string> = {
  contradicts: "Conflicts",
  extends: "Adds context",
  confirms: "Supports",
  unrelated: "Unrelated",
};

/**
 * Every value names the axis it belongs to.
 *
 * Not a style rule. These are read in three places where the axis is not on screen: fused
 * into one chip on a collapsed field row, joined by a middot in the evidence map, and as a
 * status string in the document trace. A bare "Unknown" there says nothing about what is
 * unknown, and "Direct - Mixed" left a reader guessing which word answered which question.
 *
 * It was already half-done and inconsistently: "Partly grounded" carried its axis while
 * its own siblings "Thin" and "Unknown" did not, and one copy of the outcome vocabulary
 * had drifted to "Outcome unknown" while this one still said "Unknown".
 *
 * The exception is `unsupported`. "Ungrounded" would be more parallel and less plain;
 * support is the axis under another name, and a reader loses nothing.
 */
export const GROUNDING_LABEL: Record<EvidenceAssessment["strength"], string> = {
  well_grounded: "Well grounded",
  partial: "Partly grounded",
  thin: "Thinly grounded",
  unsupported: "Unsupported",
  unknown: "Grounding unknown",
};

/** Whether prior work resembling this target exists. Never the outcome of it. */
export const PRECEDENT_LABEL: Record<PrecedentSignal["precedent"], string> = {
  direct: "Direct precedent",
  adjacent: "Adjacent precedent",
  none: "No precedent found",
  unknown: "Precedent unknown",
};

/**
 * How that prior work turned out.
 *
 * A separate axis from `PRECEDENT_LABEL`, which is why no value here says "precedent": a
 * close match can still have gone badly, and "Mixed precedent" would name the wrong thing.
 */
export const OUTCOME_LABEL: Record<PrecedentSignal["outcome"], string> = {
  favorable: "Favorable outcome",
  mixed: "Mixed outcome",
  unfavorable: "Unfavorable outcome",
  unknown: "Outcome unknown",
};

/** Present one field ref, dropping its namespace and titling each word. */
/**
 * What a development row rests on, in a reader's words.
 *
 * Rendered because the type is how a row is judged: "Phase 3" from a registry and
 * "Phase 3" from a company announcement are the same string and not equally checkable.
 * Mirrors `DEVELOPMENT_RECORD_TYPES` in `services/searcher/models.py`.
 */
const RECORD_TYPE_LABELS: Record<string, string> = {
  clinical_trial: "Trial registry",
  compound_catalog: "Compound catalog",
  regulatory_label: "Regulatory label",
  regulatory_clearance: "Regulatory clearance",
  announcement: "Announcement",
};

/**
 * Why a number the document stated was not used as a target.
 *
 * No "…, not a target" suffix: the section that lists these already says so, and three of
 * the four are not failures at all. A TB incidence trend was never a candidate for
 * calibration, so "not calibrated" would name an attempt that never happened.
 */
export const DISPOSITION_LABEL: Record<
  QuantitativeStatementDisposition["disposition"],
  string
> = {
  context_only: "Background figure",
  non_scalar: "Not a single number",
  range_or_set: "Range or set",
  uncertain: "Could not be resolved",
};

/**
 * Whether one measurement can be compared with the document's target.
 *
 * Only `unknown` spells the axis out; the other three carry it in the word itself. It is
 * read joined to a number by a middot in the excluded panel - "45% · Unknown" - where
 * nothing on screen says what is unknown about it.
 */
/**
 * How a cited source was matched, when it was not matched to a record.
 *
 * Only the fallbacks, because `canonical` is the strong case and naming it would put a line
 * on a source that has nothing wrong with it. Not a frequency argument: on a real run 40 of
 * 64 measurements were matched by title and only 24 canonically, so the fallback is the
 * common case. It is tagged because it is the weaker one, and because it is load-bearing:
 * `calibrationStatus` cannot report a verified basis unless every measurement is canonical,
 * so this is the thing that caps a cohort at "Limited".
 */
export const SOURCE_IDENTITY_CAVEAT: Record<"title_fallback" | "url_fallback", string> = {
  title_fallback: "Matched by title only",
  url_fallback: "Matched by link only",
};

/** The caveat for a status, or nothing when the source was matched to a record. */
export function sourceIdentityCaveat(status: string): string {
  return status in SOURCE_IDENTITY_CAVEAT
    ? SOURCE_IDENTITY_CAVEAT[status as keyof typeof SOURCE_IDENTITY_CAVEAT]
    : "";
}

export const SEMANTIC_STATUS_LABEL: Record<Measurement["semantic_status"], string> = {
  comparable: "Comparable",
  contextual: "Context only",
  incompatible: "Not comparable",
  unknown: "Comparability unknown",
};

/**
 * How much the comparator cohort can carry.
 *
 * Replaces "Insufficient basis" / "Limited basis" / "Broader verified basis", which asked
 * a reader to know what "basis" meant and who had "verified" it. The tiers are the
 * backend's: `sufficient` needs five comparators *and* every source identified
 * canonically, which is what "Verified" carries here - it is not a count restated, and the
 * count sits beside it.
 */
export const CALIBRATION_BASIS_LABEL: Record<Conformity["calibration_status"], string> = {
  insufficient: "Too few",
  limited: "Limited",
  sufficient: "Verified",
};

/**
 * Which column of the profile a target came from.
 *
 * Verbatim from the vocabulary. `threshold` is deliberately not "Minimum": a threshold can
 * be a ceiling - one real target is "<= 4 injections" - so naming a direction would assert
 * something the value does not carry.
 */
export const TARGET_ROLE_LABEL: Record<Conformity["target_role"], string> = {
  threshold: "Threshold",
  optimal: "Optimal",
  other: "Other target",
};

/**
 * The discovery track that surfaced an insight.
 *
 * Lower case because it is read inline ("Found by search for contrary evidence"). Worth
 * naming at all because it varies and because one is a method claim: the counterfactual
 * track exists to look for evidence *against* a target.
 */
export const QUERY_TRACK_LABEL: Record<string, string> = {
  general: "direct search",
  geographic: "geographic search",
  counterfactual: "search for contrary evidence",
  precedent: "search for prior work",
};

export function queryTrackLabel(track: string): string {
  return QUERY_TRACK_LABEL[track] ?? track.replaceAll("_", " ");
}

export function displayRecordTypeLabel(recordType: string): string {
  return RECORD_TYPE_LABELS[recordType] ?? displayAttributeLabel(recordType);
}

/**
 * The one scope that is not a document variable.
 *
 * Mirrors `PROGRAM_SCOPE_KEY` in `services/scout/models.py`. Findings retrieved by the
 * run's own questions carry it, and they reach the development landscape beside findings
 * retrieved for a variable. Left to the generic label it renders as "Program" in a list
 * of variable names, reading as a variable the document does not have.
 */
const PROGRAM_SCOPE_REF = "program";

export function displayAttributeLabel(ref: string): string {
  if (ref === PROGRAM_SCOPE_REF) return "Program-wide";
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
