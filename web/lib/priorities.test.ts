/**
 * Every tool's result is read through one shape, named the way its own page names it.
 *
 * The card's points name findings by ID and render them from these lists, so what these
 * tests pin is that each list is complete, uniquely addressed, and says exactly what the
 * page says - the drift the hand-written selectors kept producing. The model's choice of
 * what to raise is not tested here; it is the model's, and the card says so.
 */

import assert from "node:assert/strict";
import test from "node:test";

import type {
  AlignmentFinding,
  AlignmentResult,
  AlignmentVerdict,
  DocumentSpan,
  GateReview,
  InspectionReviewView,
  QuestionAssessment,
  ScoutResponse,
} from "./api.ts";
import { chainWarningText, chainWarnings } from "./aligner-chain.ts";
import { ALIGNER_PRIORITY_FOCUS, alignerPriorityFindings } from "./aligner-priorities.ts";
import { INSPECTOR_PRIORITY_FOCUS, inspectorPriorityFindings } from "./inspector-priorities.ts";
import { priorityRequest, type PriorityFinding } from "./priorities.ts";
import { SCOUT_PRIORITY_FOCUS, scoutPriorityFindings } from "./scout-priorities.ts";
import { displayAttributeLabel } from "./scout-labels.ts";
import { SCREENER_PRIORITY_FOCUS, screenerPriorityFindings } from "./screener-priorities.ts";

// --- Fixtures ------------------------------------------------------------------

function inspection(): InspectionReviewView {
  const unit = (section: string, variable: string | null, verdict: "specified" | "insufficient", blocks: string[]) => ({
    id: `${section}|${variable ?? ""}`,
    verdict,
    statement: verdict === "specified" ? "" : "Not enough is stated.",
    section_name: section,
    variable_name: variable,
    optional: false,
    cited_block_ids: blocks,
    rank: 0,
  });
  return {
    doc_id: "plan",
    applicability_facts: {},
    rubric: { id: "test", revision: null, updated_on: null, display_name: "Test", authority: "Test", scope: "Test", stage_guidance: "", mirrors: null, evidence_scope: "mapped_section", sources: [], requirements: [] },
    sections: [
      { section_name: "Profile", mapped_block_ids: [], is_present: true, verdict_counts: {} as never,
        units: [unit("Profile", "Efficacy", "insufficient", ["plan/b-1"]), unit("Profile", "Safety", "specified", ["plan/b-2"])] },
      { section_name: "Access", mapped_block_ids: [], is_present: true, verdict_counts: {} as never,
        units: [unit("Access", "Efficacy", "specified", ["plan/b-3"]), unit("Access", null, "insufficient", [])] },
    ],
    document_findings: [
      { id: "conflict|0", verdict: "section_conflict", statement: "Two sections disagree.", section_name: null,
        variable_name: null, optional: false, cited_block_ids: ["plan/b-1"], rank: 0 },
    ],
    consistency_status: "complete",
    assessment_status: "complete",
    org: null, source_type: null, intervention_class: null, indication: null,
    blocks: ["plan/b-1", "plan/b-2", "plan/b-3"].map((id) => ({ id, doc_id: "plan" })) as never,
  } as InspectionReviewView;
}

function cite(blockId: string): DocumentSpan {
  return { quote: `Content of ${blockId}.`, block_ids: [blockId] };
}

function requirement(id: string, edge: string, verdict: AlignmentVerdict, overrides: Partial<AlignmentFinding> = {}): AlignmentFinding {
  return {
    requirement_id: id, edge_id: edge, verdict, requirement: `Requirement ${id}`, statement: `About ${id}.`,
    reference_spans: [], comparison_spans: [], reference_visual_block_ids: [], comparison_visual_block_ids: [],
    ...overrides,
  };
}

function alignment(): AlignmentResult {
  return {
    documents: [
      { doc_id: "profile", source_type: "itpp", display_name: "iTPP" },
      { doc_id: "candidate", source_type: "ctpp", display_name: "cTPP" },
      { doc_id: "plan", source_type: "ipdp", display_name: "IPDP" },
    ],
    edges: [
      { edge_id: "upstream", reference_doc_id: "profile", comparison_doc_id: "candidate", question: "Q1" },
      { edge_id: "downstream", reference_doc_id: "candidate", comparison_doc_id: "plan", question: "Q2" },
    ],
    org: "bmgf", intervention_class: "vaccine", indication: "malaria", blocks: [],
    findings: [
      requirement("upstream/r-1", "upstream", "falls_short", { comparison_spans: [cite("candidate/b-42")] }),
      requirement("downstream/r-1", "downstream", "meets", {
        reference_spans: [cite("candidate/b-42")], comparison_spans: [cite("plan/b-7")],
      }),
      requirement("downstream/r-2", "downstream", "exceeds"),
    ],
  };
}

function scout(): ScoutResponse {
  const field = (name: string, target: string, resolved = true) => ({
    name, description: "", block_ids: [`doc/${name}`], document_target: target, document_spans: [],
    definition_mode: "fixed", target_resolved: resolved, target_resolution_reason: "", evidence_domain: "clinical",
    entities: [], quantitative_target_ids: [], quantitative_statement_dispositions: [],
    quantitative_target_status: "present", quantitative_target_status_reason: "",
  });
  const insight = (ref: string | null, statement: string) => ({
    id: statement, statement, query: "q", supporting_findings: [], org: null, source_type: null,
    intervention_class: null, indication: null, attribute_ref: ref,
  });
  return {
    variables: [field("vaccine.hiv_incidence", "at least 80% reduction"), field("vaccine.dose_volume", "", false)],
    assessments: [{ attribute_ref: "vaccine.hiv_incidence", strength: "thin", reason: "One small trial.",
      doc_target: "at least 80% reduction", doc_block_ids: ["doc/a"], supporting_insight_ids: [], supporting_findings: [] }],
    matches: [
      { relation: "contradicts", reason: "Reported 40%.", doc_block_ids: ["doc/m"], insight: insight("vaccine.hiv_incidence", "Observed 40%.") },
      { relation: "confirms", reason: "Agrees.", insight: insight("vaccine.hiv_incidence", "Observed 85%.") },
      { relation: "contradicts", reason: "Cost differs.", insight: insight(null, "Program cost is higher.") },
      { relation: "unrelated", reason: "Off topic.", insight: insight("vaccine.dose_volume", "Unrelated.") },
    ],
    conformity: [{ attribute_refs: ["vaccine.hiv_incidence"], target_id: "t1", target_label: "Constructed summary",
      target_quote: "at least 80% reduction", target_meeting_count: 0, target_meeting_rate: 0,
      verdict: "0 of 12 admitted comparators meet the document target", benchmark_count: 12,
      calibration_status: "sufficient", doc_block_ids: [] }],
    precedents: [],
  } as unknown as ScoutResponse;
}

function gate(): GateReview {
  const question = (id: string, state: QuestionAssessment["state"], overrides: Partial<QuestionAssessment> = {}): QuestionAssessment => ({
    id, text: `Question ${id}?`, state, requirement: "required", statement: "", missing: "", cited_block_ids: [], ...overrides,
  });
  return {
    gate_id: "ep1", gate_label: "End of Phase 1", bank_source: "fixture", documents: [{ doc_id: "plan" }],
    disciplines: [
      { id: "cmc", label: "CMC", questions: [
        question("q1", "partly_answered", { statement: "Route is named.", missing: "No yield is given.", cited_block_ids: ["plan/b-1"] }),
        question("q2", "not_found", { requirement: "anticipatory" }),
      ] },
      { id: "clin", label: "Clinical", questions: [question("q3", "answered", { statement: "Stated.", cited_block_ids: ["plan/b-2"] })] },
    ],
    org: "bmgf", intervention_class: "drug", indication: "malaria", blocks: [],
  };
}

const LENSES: [string, PriorityFinding[], string][] = [
  ["inspector", inspectorPriorityFindings(inspection()), INSPECTOR_PRIORITY_FOCUS],
  ["aligner", alignerPriorityFindings(alignment()), ALIGNER_PRIORITY_FOCUS],
  ["scout", scoutPriorityFindings(scout()), SCOUT_PRIORITY_FOCUS],
  ["screener", screenerPriorityFindings(gate()), SCREENER_PRIORITY_FOCUS],
];

// --- The shared contract ------------------------------------------------------

test("every tool addresses each finding once, so a point can name it unambiguously", () => {
  for (const [tool, findings] of LENSES) {
    const ids = findings.map((finding) => finding.id);
    assert.equal(new Set(ids).size, ids.length, `${tool} repeats a finding id`);
  }
});

test("every finding has a subject and at least one verdict in the tool's words", () => {
  for (const [tool, findings] of LENSES) {
    for (const finding of findings) {
      assert.ok(finding.subject.trim(), `${tool} has a finding with no subject`);
      assert.ok(finding.verdicts.length > 0, `${tool}'s ${finding.id} carries no verdict`);
    }
  }
});

test("every tool states what its reader needs first", () => {
  for (const [tool, , focus] of LENSES) assert.ok(focus.trim(), `${tool} has no focus sentence`);
});

test("the request leaves passages behind: the model points at findings, never at blocks", () => {
  const request = priorityRequest({
    authority: "A", focus: "F", findings: LENSES[0][1], org: "", interventionClass: "", indication: "",
  });
  for (const finding of request.findings) {
    assert.equal("blockIds" in finding, false);
    assert.ok(finding.statements.every(Boolean), "an empty statement reaches the model");
  }
});

// --- Inspector ---------------------------------------------------------------

test("Inspector reads every unit of the rubric, and not the run-wide consistency check", () => {
  const findings = inspectorPriorityFindings(inspection());
  assert.deepEqual(findings.map((finding) => finding.id), ["Profile|Efficacy", "Profile|Safety", "Access|Efficacy", "Access|"]);
});

test("Inspector keeps the section, so two units with one name are told apart", () => {
  const [profile, , access, sectionOnly] = inspectorPriorityFindings(inspection());
  assert.equal(profile.subject, "Efficacy");
  assert.equal(profile.group, "Profile");
  assert.equal(access.group, "Access");
  // A unit that is the section itself is named by it, not grouped under it a second time.
  assert.equal(sectionOnly.subject, "Access");
  assert.equal(sectionOnly.group, undefined);
  assert.deepEqual(profile.verdicts, ["Insufficient"]);
});

// --- Aligner -----------------------------------------------------------------

test("Aligner reads every requirement under the comparison that judged it", () => {
  const findings = alignerPriorityFindings(alignment());
  assert.deepEqual(findings.map((finding) => finding.id), ["upstream/r-1", "downstream/r-1", "downstream/r-2"]);
  assert.equal(findings[0].group, "iTPP → cTPP");
  assert.deepEqual(findings[0].verdicts, ["Falls short"]);
});

test("Aligner carries an upstream flag as a code note, never as a model's statement", () => {
  const result = alignment();
  const met = alignerPriorityFindings(result)[1];
  const [warning] = chainWarnings(result).get("downstream/r-1") ?? [];
  assert.deepEqual(met.notes, [chainWarningText(warning)]);
  assert.deepEqual(met.statements, ["About downstream/r-1."]);
  assert.ok(met.blockIds.includes("candidate/b-42"), "the shared passage is not openable");
});

// --- Scout -------------------------------------------------------------------

test("Scout names a field exactly as its Fields tab does", () => {
  const [incidence] = scoutPriorityFindings(scout());
  assert.equal(incidence.subject, displayAttributeLabel("vaccine.hiv_incidence"));
  assert.equal(incidence.subject, "HIV Incidence");
});

test("Scout keeps each axis as its own verdict, and code's counts out of the statements", () => {
  const [incidence] = scoutPriorityFindings(scout());
  assert.deepEqual(incidence.verdicts, [
    "Thinly grounded",
    "Conflicts: 1 insight",
    "Supports: 1 insight",
    "at least 80% reduction: 0 of 12 admitted comparators meet the document target (12 measured)",
  ]);
  assert.ok(incidence.statements.every((statement) => !statement.includes("comparators meet")));
  assert.deepEqual(incidence.statements, ["One small trial.", "Observed 40%.", "Reported 40%."]);
});

test("Scout quotes the document's own words, never a summary it built", () => {
  const [incidence, volume] = scoutPriorityFindings(scout());
  assert.equal(incidence.quote, "at least 80% reduction");
  assert.ok(!incidence.verdicts.join(" ").includes("Constructed summary"));
  // An unresolved target has no words of the document's to quote.
  assert.equal(volume.quote, undefined);
});

test("Scout keeps a contradiction that names no field, rather than dropping it", () => {
  const program = scoutPriorityFindings(scout()).find((finding) => finding.id === "program");
  assert.ok(program, "the program-wide contradiction vanished");
  assert.deepEqual(program.verdicts, ["Conflicts: 1 insight"]);
});

// --- Screener ----------------------------------------------------------------

test("Screener reads every question in full, with its state, requirement and discipline", () => {
  const findings = screenerPriorityFindings(gate());
  assert.deepEqual(findings.map((finding) => finding.id), ["q1", "q2", "q3"]);
  assert.equal(findings[0].subject, "Question q1?");
  assert.equal(findings[0].group, "CMC");
  assert.deepEqual(findings[1].verdicts, ["Not found", "Anticipatory"]);
});

test("Screener labels what a partial answer leaves open, so it is not read as the answer", () => {
  const [partial] = screenerPriorityFindings(gate());
  assert.ok(partial.statements.includes("Still open: No yield is given."));
});
