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
import type { Tone } from "./tone.ts";
import type {
  Conformity,
  EvidenceAssessment,
  FailureCode,
  Match,
  Measurement,
  PrecedentSignal,
  QuantitativeLedgerReview,
  QuantitativeStatementDisposition,
  TargetMappingIssueCode,
} from "./api.ts";
import { ACRONYMS } from "./display-label.ts";

/**
 * `not_assessed` on every axis below is not a reading. It is what the pipeline records when
 * the stage obtained no verdict - a model call failed - so its label says that and its tone
 * is neutral. Filed as "Unrelated" or "unknown" it would claim the evidence was read and
 * was silent, which is the one thing nobody observed.
 *
 * `no_evidence`, on grounding and both precedent axes, is the other state only code records:
 * nothing retrieved reached the field, so no model was asked. Nothing failed and nothing was
 * judged, so it is neutral and named apart from both `unknown` and `not_assessed`; its
 * reason is empty and the interface explains it in its own voice (`verdictNote`).
 *
 * `not_searched` is the third: the reviewer left the field out of evidence search at target
 * review, so no search ran. It is a choice rather than an observation, and it is the same
 * fact on every axis, so it reads the same on each and is named once.
 */
export const RELATIONSHIP_LABEL: Record<Match["relation"], string> = {
  contradicts: "Conflicts",
  extends: "Adds context",
  confirms: "Supports",
  unrelated: "Unrelated",
  not_assessed: "Not assessed",
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
  no_evidence: "No evidence to ground",
  not_searched: "Not searched",
  not_assessed: "Grounding not assessed",
};

/** Whether prior work resembling this target exists. Never the outcome of it. */
/**
 * The tone each grounding verdict carries. Only the tone.
 *
 * Beside `GROUNDING_LABEL` for the reason stated there: the word and the colour are one
 * decision about one verdict, and split across files they drift. They had, twice - the
 * page held this map in tone words while the evidence map held it in colour words
 * (`green`, `blue`, `amber`), so a strength was `info` in one tab and `blue` in another
 * and nothing connected them.
 */
export const GROUNDING_TONE: Record<EvidenceAssessment["strength"], Tone> = {
  well_grounded: "success",
  partial: "info",
  thin: "warning",
  unsupported: "danger",
  unknown: "neutral",
  no_evidence: "neutral",
  not_searched: "neutral",
  not_assessed: "neutral",
};

export const PRECEDENT_LABEL: Record<PrecedentSignal["precedent"], string> = {
  direct: "Direct precedent",
  adjacent: "Adjacent precedent",
  none: "No precedent found",
  unknown: "Precedent unknown",
  no_evidence: "No evidence on precedent",
  not_searched: "Not searched",
  not_assessed: "Precedent not assessed",
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
  no_evidence: "No evidence on outcome",
  not_searched: "Not searched",
  not_assessed: "Outcome not assessed",
};

/**
 * Both precedent axes as one status: "Direct precedent · Mixed outcome".
 *
 * One classification decides both, so a failure leaves both `not_assessed` and is named
 * once - the pair would say one fact twice. The same holds for `no_evidence` and
 * `not_searched`.
 */
export function precedentStatusLabel(
  signal: Pick<PrecedentSignal, "precedent" | "outcome">,
): string {
  if (!outcomeIsSeparate(signal)) return PRECEDENT_LABEL[signal.precedent];
  return `${PRECEDENT_LABEL[signal.precedent]} · ${OUTCOME_LABEL[signal.outcome]}`;
}

/**
 * Whether the outcome is a reading of its own, to name beside coverage.
 *
 * Not when code recorded both axes at once - a failure, no evidence, or a field left out at
 * review - because then the pair would say one fact twice.
 */
export function outcomeIsSeparate(signal: Pick<PrecedentSignal, "precedent">): boolean {
  return !isCodeRecorded(signal.precedent);
}

/** A state only code records: no model call, so no model reason. */
function isCodeRecorded(verdict: string): boolean {
  return verdict === "not_assessed" || verdict === "no_evidence" || verdict === "not_searched";
}

/**
 * The model's reason for a verdict, or nothing when no verdict was obtained.
 *
 * On `not_assessed` the reason field holds the pipeline's diagnostic - the failed call's
 * message - not a model's sentence. Rendered where a reading goes it would put code's words
 * in a model's voice; the label already says what happened, and the message stays in the
 * saved result for diagnosis.
 */
export function verdictReason(verdict: string, reason: string): string {
  return isCodeRecorded(verdict) ? "" : reason;
}

/**
 * What the interface says in place of a reason, where code recorded the state and no model
 * wrote one. Rendered as the interface's note, never as a reading.
 *
 * `no_evidence` and `not_searched`: a failure's label already says what happened.
 */
export function verdictNote(verdict: string): string {
  if (verdict === "no_evidence") {
    return "Nothing this run retrieved bore on this field, so there was no evidence to judge.";
  }
  return verdict === "not_searched"
    ? "Excluded at review, so Scout did not search for evidence on this field."
    : "";
}

/**
 * Why an independent review gave no recommendation, by its failure code.
 *
 * The recorded reason on an `unavailable` review is the failed call's message, a diagnostic
 * kept in the saved result; worded from the code, the page never shows it as a sentence.
 */
export const REVIEW_FAILURE_LABEL: Record<FailureCode, string> = {
  response_truncated: "The reviewer's answer was cut off before it finished.",
  response_refused: "The reviewer declined to answer.",
  invalid_model_response: "The reviewer's answer could not be used, even after a retry.",
  provider_error: "The model provider failed before the reviewer answered.",
};

/** The explanation under an independent recommendation: the model's reason, or its failure in words. */
export function reviewRecommendationReason(review: {
  ai_recommendation: string;
  ai_review_failure_code: FailureCode | "";
  ai_review_reason: string;
}): string {
  if (review.ai_recommendation !== "unavailable") return review.ai_review_reason;
  return review.ai_review_failure_code
    ? REVIEW_FAILURE_LABEL[review.ai_review_failure_code]
    : "The independent review returned no recommendation.";
}

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
/** What a relation means for the document, on the shared scale. */
export const RELATIONSHIP_TONE: Record<Match["relation"], Tone> = {
  contradicts: "danger",
  extends: "warning",
  confirms: "success",
  unrelated: "neutral",
  not_assessed: "neutral",
};

/**
 * Whether prior work of this kind went well. Never whether it resembles this target.
 *
 * `PRECEDENT_LABEL` needs no matching map: every value there is neutral, because how
 * closely prior work matches this target is not good or bad news on its own.
 */
export const OUTCOME_TONE: Record<PrecedentSignal["outcome"], Tone> = {
  favorable: "success",
  mixed: "warning",
  unfavorable: "danger",
  unknown: "neutral",
  no_evidence: "neutral",
  not_searched: "neutral",
  not_assessed: "neutral",
};

export const DISPOSITION_LABEL: Record<
  QuantitativeStatementDisposition["disposition"],
  string
> = {
  context_only: "Background figure",
  non_scalar: "Not a single number",
  range_or_set: "Range or set",
  uncertain: "Could not be resolved",
  mapping_failed: "Extraction failed",
};

/**
 * Each structural check a proposed target can fail, in a reviewer's words.
 *
 * Keyed by the code the stage records, so the page chooses its wording from the code
 * rather than from the reason's prose - the reason is a sentence, and rewording it once
 * silently changed what a reviewer was told.
 */
export const TARGET_MAPPING_ISSUE_LABEL: Record<TargetMappingIssueCode, string> = {
  invalid_target_list: "the proposed targets were not a list",
  invalid_target_object: "a proposed target was malformed",
  missing_field_links: "no field link",
  invalid_field_links: "no resolved field it defines or constrains",
  invalid_target_expression: "the number could not be normalized",
  target_expression_must_be_bound: "not an exact value or a directional bound",
  invalid_target_role: "no valid target role",
  invalid_target_semantic_profile: "an incomplete description of what is measured",
  invalid_target_comparison_contract: "incomplete comparison rules",
  invalid_target_quote: "the excerpt is not exact source text",
  invalid_semantic_provenance: "qualifiers not tied to the source passage",
  missing_target_provenance: "no source excerpt",
  invalid_target_provenance: "the excerpt is not tied to its source passage",
  duplicate_atomic_target: "the same target was proposed twice",
  missing_target_mapping: "no target was proposed",
};

/**
 * Why a document statement's numeric review did not finish, for the reviewer deciding it.
 *
 * Decided by the classification and the recorded codes alone. A statement with no failure
 * code was classified by the model, so its reason is the model's and is returned as it is.
 */
export function statementReviewReason(
  review: Pick<QuantitativeLedgerReview, "failure_code" | "issue_codes" | "reason"> & {
    /** A ledger review's classification, or a field disposition's `disposition`. */
    classification: QuantitativeLedgerReview["classification"] | QuantitativeStatementDisposition["disposition"];
  },
): string {
  const kept = review.classification === "partial_target";
  const checks = review.issue_codes.map((code) => TARGET_MAPPING_ISSUE_LABEL[code]);
  const failed = checks.length ? ` Failed checks: ${checks.join("; ")}.` : "";
  if (review.failure_code === "invalid_target_mapping") {
    return kept
      ? `Validated targets from this passage were kept. A separate proposed mapping could not be verified and remains outside retrieval and statistics.${failed}`
      : `Scout could not create a complete, source-verifiable target from this statement. It remains outside retrieval and statistics.${failed}`;
  }
  if (review.failure_code === "invalid_model_response") {
    return kept
      ? "Validated targets from this passage were kept. Scout could not resolve the rest of it into one reliable review decision, so that part remains outside retrieval and statistics."
      : "Scout could not resolve this statement into one reliable review decision. It remains outside retrieval and statistics.";
  }
  return review.reason;
}

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
 * Only the fallback, because `canonical` is the strong case and naming it would put a line
 * on a source that has nothing wrong with it. It is tagged because it is the weaker one,
 * and because it is load-bearing:
 * `calibrationStatus` cannot report a verified basis unless every measurement is canonical,
 * so this is the thing that caps a cohort at "Limited".
 */
export const SOURCE_IDENTITY_CAVEAT: Record<Exclude<Measurement["source_identity_status"], "canonical">, string> = {
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
  adjacent: "search for comparable work",
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

/**
 * A variable's name in sentence case: "Duration of protection", "COGS".
 *
 * Sentence case because a variable name is a phrase, not a title, and Drafter and Scout
 * name the same variables: one wrote "Duration of protection" and the other "Duration Of
 * Protection", so a reader moving between the two met one variable under two names.
 */
export function displayAttributeLabel(ref: string): string {
  if (ref === PROGRAM_SCOPE_REF) return "Program-wide";
  const local = ref.includes(".") ? ref.split(".").slice(1).join(".") : ref;
  return local
    .replace(/[._-]+/g, " ")
    .split(" ")
    .filter(Boolean)
    .map((word, index) => {
      const lower = word.toLowerCase();
      if (ACRONYMS.has(lower)) return lower.toUpperCase();
      return index === 0 ? lower.charAt(0).toUpperCase() + lower.slice(1) : lower;
    })
    .join(" ");
}

/** Prefer the lane label a source adapter supplied over a derived one. */
const SOURCE_LABELS: Record<string, string> = {
  pubmed: "PubMed",
  clinicaltrials: "ClinicalTrials.gov",
  isrctn: "ISRCTN",
  ctis: "CTIS",
  fda: "FDA Regulatory",
  fda_safety: "FDA Safety",
  europepmc: "Europe PMC",
  who_guidelines: "WHO Guidelines",
};

export function sourceDisplayLabel(
  source: string,
  labels?: Record<string, string>,
): string {
  return (
    labels?.[source] ?? SOURCE_LABELS[source] ??
    source
      .replace(/[_-]+/g, " ")
      .replace(/\b\w/g, (character) => character.toUpperCase())
  );
}
