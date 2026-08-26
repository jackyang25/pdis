import { ALIGNMENT_VERDICTS } from "./api.ts";
import type {
  AlignerResponse,
  DisciplineReview,
  ExpertResponse,
  InspectorResponse,
  QuestionAssessment,
  ScoutResponse,
} from "./api.ts";

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
export type ResultType = "aligner" | "expert" | "inspector" | "scout";

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
 * and the one derived value the interface reads rather than recomputes.
 *
 * A unit *is* its assessment - one `verdict`, one `statement` - so there is nothing
 * nested to walk. This used to descend into `units[].findings[]` and require a
 * `reason`, a `level` and a unit `status` on the way, which is why a result built by
 * the current pipeline stopped hydrating the moment those three went: the check was
 * written against the shape rather than against what the interface needs.
 *
 * `verdict_counts` is checked because it is derived during serialization, so it is
 * exactly what an older file will be missing - and a file without it renders every
 * section header blank.
 *
 * `statement` is deliberately not required. It is empty on a sound unit, which is most
 * of them, so requiring text would reject a clean document.
 */
function assertInspectorReadable(result: unknown): void {
  const inspection = (result as InspectorResponse | null)?.inspection;
  if (!inspection) fail("inspector", "it carries no assessment");

  for (const section of requireArray("inspector", inspection.sections, "sections")) {
    const entry = section as Record<string, unknown>;
    requireText("inspector", entry.section_name, "a section name");
    if (typeof entry.verdict_counts !== "object" || entry.verdict_counts === null) {
      fail("inspector", `section ${String(entry.section_name)} has no verdict counts`);
    }
    for (const unit of requireArray("inspector", entry.units, "a section's units")) {
      requireText("inspector", (unit as Record<string, unknown>).verdict, "a unit verdict");
    }
  }
  requireArray("inspector", inspection.document_findings, "document_findings");
}

// --- Aligner -----------------------------------------------------------------

/**
 * What an alignment must contain to be rendered.
 *
 * Documents and comparisons that refer to each other, and findings that refer to a
 * comparison this file actually made. The service checks far more — that each side's
 * citations land in that side's document, that a shortfall names its gap — and cannot be
 * repeated here, because those checks read the parsed blocks. What is repeated is
 * whatever the view would otherwise crash on, or silently render as empty.
 */
function assertAlignerReadable(result: unknown): void {
  const alignment = (result as AlignerResponse | null)?.alignment;
  if (!alignment) fail("aligner", "it carries no alignment");
  const documents = requireArray("aligner", alignment.documents, "documents");
  if (documents.length < 2) fail("aligner", "it names fewer than two documents");
  const known = new Set(
    documents.map((document) => (document as { doc_id?: string }).doc_id),
  );
  const edges = requireArray("aligner", alignment.edges, "comparisons");
  if (edges.length === 0) fail("aligner", "it carries no comparison");
  const edgeIds = new Set<string>();
  for (const edge of edges as AlignerResponse["alignment"]["edges"]) {
    if (!known.has(edge.reference_doc_id) || !known.has(edge.comparison_doc_id)) {
      fail("aligner", "a comparison names a document the file does not carry");
    }
    edgeIds.add(edge.edge_id);
  }

  // Zero findings is not an empty result to be rendered quietly: a run that compared
  // nothing looks identical to one that found nothing wrong, which is the confusion the
  // whole tool exists to prevent.
  const findings = requireArray("aligner", alignment.findings, "findings");
  if (findings.length === 0) fail("aligner", "it carries no findings");
  for (const finding of findings as AlignerResponse["alignment"]["findings"]) {
    if (!edgeIds.has(finding.edge_id)) {
      fail("aligner", "a finding names a comparison the file does not carry");
    }
    if (!ALIGNMENT_VERDICTS.includes(finding.verdict)) {
      fail("aligner", `a finding carries an unknown verdict (${finding.verdict})`);
    }
    requireText("aligner", finding.requirement, "a finding's requirement");
  }
}

// --- Expert ------------------------------------------------------------------

/**
 * What a gate review must contain to be rendered.
 *
 * The completeness check the service enforces cannot be repeated here, because a
 * file carries no bank to compare against — which is exactly why every question
 * carries its own `text`. So this checks the two things a reader depends on: that
 * each question can be displayed, and that an answer's evidence matches the source
 * it claims. A `context` answer with a block ID would render as checkable when it
 * is not, and that is the one way this result can mislead.
 */
function assertExpertReadable(result: unknown): void {
  const review = (result as ExpertResponse | null)?.review;
  if (!review) fail("expert", "it carries no gate review");
  requireText("expert", review.gate_id, "the gate");
  requireText("expert", review.gate_label, "the gate label");
  if (requireArray("expert", review.documents, "documents").length === 0) {
    fail("expert", "it names no document");
  }
  const labels = new Set(review.context_labels ?? []);
  const blocks = new Set((review.blocks ?? []).map((block) => block.id));

  const disciplines = requireArray("expert", review.disciplines, "disciplines");
  if (disciplines.length === 0) fail("expert", "it carries no discipline");
  let questions = 0;
  for (const entry of disciplines as DisciplineReview[]) {
    requireText("expert", entry.label, "a discipline label");
    for (const question of requireArray("expert", entry.questions, "questions")) {
      const held = question as QuestionAssessment;
      questions += 1;
      requireText("expert", held.id, "a question id");
      requireText("expert", held.text, "a question's text");
      requireText("expert", held.state, "a question state");
      if (held.state === "partly_answered" && !held.missing?.trim()) {
        fail("expert", "a partial answer does not say what it leaves open");
      }
      if (held.state !== "answered" && held.state !== "partly_answered") {
        // An older file's `absent`, `not_answerable`, or `not_assessable` reaches here
        // as an unknown string. The version gate is what actually refuses it; this only
        // keeps such a file from rendering blank rows if the gate is ever bypassed.
        if (!["not_applicable", "not_found"].includes(held.state)) {
          fail("expert", `it uses a question state this version cannot read: ${held.state}`);
        }
        continue;
      }
      if (held.source === "document") {
        if ((held.cited_block_ids ?? []).length === 0) {
          fail("expert", "an answer from a document cites no passage");
        }
        if (held.cited_block_ids.some((id) => !blocks.has(id))) {
          fail("expert", "an answer cites a passage the file does not carry");
        }
      } else if (held.source === "context") {
        if ((held.cited_block_ids ?? []).length > 0) {
          fail("expert", "an answer from supplied context cites a passage");
        }
        if (!labels.has(held.context_label)) {
          fail("expert", "an answer names a context item the file does not list");
        }
      } else {
        fail("expert", "an answered question does not say where the answer came from");
      }
    }
  }
  if (questions === 0) fail("expert", "it carries no question");
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
  expert: assertExpertReadable,
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
  // Burden indicators are deliberately absent: a disease reading is not experimental or
  // comparator, and not direct or analogous to a target. It carries no role to check.
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
