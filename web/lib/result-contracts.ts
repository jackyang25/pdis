import type { AlignerResponse, InspectorResponse, ScoutResponse } from "./api.ts";

/**
 * What each tool's saved analysis must contain to be readable.
 *
 * Kept out of `result-file.ts` on purpose: that module owns the envelope - schema,
 * versions, state, and how documents travel beside an analysis - and knows nothing
 * about any tool's shape. This module owns the per-tool part, one entry each, so a
 * reader comparing the three sees one pattern rather than Scout's 150 lines of
 * semantics inline and one `if` for the other two.
 *
 * These sit outside every functional pipeline. Nothing here runs during an
 * analysis; it runs only at the import boundary, on a file someone hands us.
 *
 * They are a backstop, not the decision. The per-tool `analysis_version` decides
 * validity, because it is the only signal that catches a change in what a field
 * *means* while its name and type survive. A field check cannot see that. What it
 * does catch is the version gate's weak point: a shape changed and the number not
 * bumped, which would otherwise reach the interface as a broken render instead of a
 * clear refusal.
 */

/** The tools that produce a downloadable result. */
export type ResultType = "aligner" | "inspector" | "scout";

/** Throws with the reason this analysis cannot be hydrated. */
export type ResultContract = (result: unknown) => void;

function fail(tool: ResultType, reason: string): never {
  throw new Error(`this ${tool} result cannot be read: ${reason}`);
}

function requireArray(tool: ResultType, value: unknown, name: string): unknown[] {
  if (!Array.isArray(value)) fail(tool, `${name} is missing or not a list`);
  return value as unknown[];
}

function requireText(tool: ResultType, value: unknown, name: string): void {
  if (typeof value !== "string" || !value.trim()) fail(tool, `${name} is missing`);
}

// --- Inspector ---------------------------------------------------------------

/**
 * The minimum an Inspector assessment needs: every section, every unit beneath it,
 * and the derived values the interface reads rather than recomputes.
 *
 * Derived values are checked because they are exactly what an older file will be
 * missing: `status`, `level`, and `status_counts` were added when per-dimension
 * verdicts were replaced, and a file without them would render every unit blank.
 */
function assertInspectorReadable(result: unknown): void {
  const inspection = (result as InspectorResponse | null)?.inspection;
  if (!inspection) fail("inspector", "it carries no assessment");

  for (const section of requireArray("inspector", inspection.sections, "sections")) {
    const entry = section as Record<string, unknown>;
    requireText("inspector", entry.section_name, "a section name");
    if (typeof entry.status_counts !== "object" || entry.status_counts === null) {
      fail("inspector", `section ${String(entry.section_name)} has no status counts`);
    }
    for (const unit of requireArray("inspector", entry.units, "a section's units")) {
      const held = unit as Record<string, unknown>;
      requireText("inspector", held.status, "a unit status");
      for (const finding of requireArray("inspector", held.findings, "a unit's findings")) {
        const raised = finding as Record<string, unknown>;
        requireText("inspector", raised.reason, "a finding reason");
        requireText("inspector", raised.statement, "a finding statement");
        requireText("inspector", raised.level, "a finding level");
      }
    }
  }
  requireArray("inspector", inspection.document_findings, "document_findings");
}

// --- Aligner -----------------------------------------------------------------

function assertAlignerReadable(result: unknown): void {
  const alignment = (result as AlignerResponse | null)?.alignment;
  if (!alignment) fail("aligner", "it carries no alignment");
  requireArray("aligner", alignment.units, "units");
  requireArray("aligner", alignment.links, "links");
  if (!alignment.reference_document || !alignment.comparison_document) {
    fail("aligner", "it does not name both documents");
  }
}

// --- Scout -------------------------------------------------------------------

/**
 * Scout checks more than readability, and for a real reason: its review workflow can
 * produce a draft whose fields are all present and whose evidence is not yet
 * admitted. The other two tools have no draft state, so they have nothing equivalent
 * to check. The structure is shared; the depth is each tool's own.
 */
function assertScoutReadable(result: unknown): void {
  const scout = result as ScoutResponse;
  if (
    !isScoutResultFinal(scout)
    || !hasCompleteComparisonContract(scout)
    || !hasCompleteEvidenceUnitContract(scout)
  ) {
    fail("scout", "its quantitative evidence contract is incomplete");
  }
  if (!hasCompleteProjectionRoleContract(scout)) {
    fail("scout", "its projection role contract is incomplete");
  }
  if (!hasCompleteSafetyObservationContract(scout)) {
    fail("scout", "its safety observation contract is incomplete");
  }
}

/**
 * One entry per tool, so adding a tool is adding a row here.
 *
 * `satisfies` rather than an annotation: a tool added to `ResultType` without a
 * contract fails to compile instead of silently importing unchecked.
 */
export const RESULT_CONTRACTS = {
  aligner: assertAlignerReadable,
  inspector: assertInspectorReadable,
  scout: assertScoutReadable,
} as const satisfies Record<ResultType, ResultContract>;

function hasCompleteEvidenceUnitContract(result: ScoutResponse): boolean {
  return (result.conformity ?? []).every((score) => {
    const admittedIds = score.measurements.map((measurement) => measurement.evidence_unit_id);
    return admittedIds.every(Boolean)
      && new Set(admittedIds).size === admittedIds.length
      && score.measurements.every((measurement) =>
        Boolean(measurement.evidence_unit)
          && ["approved", "auto_admitted"].includes(measurement.admission_status)
      )
      && score.excluded_measurements.every((measurement) =>
        Boolean(measurement.evidence_unit_id)
          && Boolean(measurement.evidence_unit)
          && !["approved", "auto_admitted"].includes(measurement.admission_status)
      );
  });
}

function semanticFields(): string[] {
  return [
    "measure", "endpoint", "intervention", "population", "regimen",
    "time_horizon", "statistic", "conditions",
  ];
}

function hasCompleteComparisonContract(value: unknown): boolean {
  const result = value as { quantitative_ledger?: { targets?: unknown } } | null;
  const targets = result?.quantitative_ledger?.targets;
  if (!Array.isArray(targets)) return false;
  const fields = semanticFields();
  return targets.every((target) => {
    if (!target || typeof target !== "object") return false;
    const contract = (target as Record<string, unknown>).comparison_contract;
    if (!contract || typeof contract !== "object" || Array.isArray(contract)) return false;
    const rules = contract as Record<string, unknown>;
    if (Object.keys(rules).length !== fields.length || fields.some((field) => !(field in rules))) {
      return false;
    }
    return fields.every((field) => {
      const rule = rules[field] as Record<string, unknown> | null;
      if (!rule || typeof rule !== "object" || Array.isArray(rule)) return false;
      const mode = rule.mode;
      const scope = typeof rule.scope === "string" ? rule.scope.trim() : "";
      const reason = typeof rule.reason === "string" ? rule.reason.trim() : "";
      if (!["exact", "compatible", "unconstrained", "unknown"].includes(String(mode))) {
        return false;
      }
      if (field === "measure" && mode !== "exact") return false;
      if ((mode === "exact" || mode === "compatible") && !scope) return false;
      if (mode === "unconstrained" && scope) return false;
      return mode !== "unknown" || Boolean(reason);
    });
  });
}

function hasCompleteProjectionRoleContract(value: unknown): boolean {
  const result = value as {
    development_landscape?: unknown;
    safety_observations?: unknown;
  } | null;
  const sourceRoles = new Set([
    "experimental", "comparator", "control", "co_intervention", "unknown",
  ]);
  const relationships = new Set([
    "direct", "analogous", "adjacent", "unrelated", "unknown",
  ]);
  const projections = [result?.development_landscape, result?.safety_observations];
  return projections.every((items) => Array.isArray(items) && items.every((item) => {
    if (!item || typeof item !== "object" || Array.isArray(item)) return false;
    const projection = item as Record<string, unknown>;
    return typeof projection.projection_id === "string"
      && Boolean(projection.projection_id.trim())
      && sourceRoles.has(String(projection.source_role))
      && relationships.has(String(projection.target_relationship))
      && typeof projection.target_relationship_reason === "string";
  }));
}

function hasCompleteSafetyObservationContract(value: unknown): boolean {
  const recordTypes = new Set([
    "label_warning", "reported_event", "device_event", "recall",
  ]);
  const sourceSystems = new Set([
    "fda_label", "faers", "maude", "fda_recall",
  ]);
  const visit = (node: unknown): boolean => {
    if (Array.isArray(node)) return node.every(visit);
    if (!node || typeof node !== "object") return true;
    const record = node as Record<string, unknown>;
    const observations = record.safety_observations;
    if (observations !== undefined) {
      if (!Array.isArray(observations) || !observations.every((item) => {
        if (!item || typeof item !== "object" || Array.isArray(item)) return false;
        const observation = item as Record<string, unknown>;
        const count = observation.report_count;
        const sourceSystem = String(observation.source_system);
        const validCount = sourceSystem === "faers"
          ? Number.isInteger(count) && Number(count) >= 0
          : count === null;
        return typeof observation.product_name === "string"
          && Boolean(observation.product_name.trim())
          && recordTypes.has(String(observation.record_type))
          && sourceSystems.has(sourceSystem)
          && typeof observation.label === "string"
          && Boolean(observation.label.trim())
          && typeof observation.detail === "string"
          && validCount
          && typeof observation.qualification === "string";
      })) return false;
    }
    return Object.values(record).every(visit);
  };
  return visit(value);
}

/** Pending admissions make a Scout analysis a review draft, not a final result. */
export function pendingQuantitativeReviewCount(result: ScoutResponse): number {
  const targetReviews = (result.quantitative_ledger?.targets ?? [])
    .filter((target) => target.review_status === "needs_review").length;
  const statementReviews = (result.quantitative_ledger?.reviews ?? [])
    .filter((review) => review.review_status === "needs_review").length;
  const evidenceReviews = (result.conformity ?? []).reduce(
    (total, score) => total + [...score.measurements, ...score.excluded_measurements]
      .filter((measurement) => measurement.admission_status === "needs_review")
      .length,
    0,
  );
  return targetReviews + statementReviews + evidenceReviews;
}

export function isScoutResultFinal(result: ScoutResponse): boolean {
  return result.phase === "final" && pendingQuantitativeReviewCount(result) === 0;
}
