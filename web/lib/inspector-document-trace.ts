import type {
  ContentBlock,
  DimensionGrade,
  DimensionName,
  Grade,
  InspectionResult,
  SectionGrade,
  VariableGrade,
} from "./api.ts";
import { DIMENSION_NAMES } from "./api.ts";
import type {
  DocumentAnnotation,
  DocumentAnnotationEmphasis,
} from "./document-trace.ts";

/**
 * Projects an existing `InspectionResult` into shared document annotations.
 *
 * Pure and order-preserving. It selects, labels, and references existing grades;
 * it never re-grades, re-parses prose, or infers lineage the result does not
 * already carry.
 *
 * Inspector carries no exact quotes — only `block_ids` — so annotations claim
 * whole blocks rather than spans. Synthesizing a span by searching block text for
 * a variable name would invent provenance the model never asserted.
 */

export type InspectorDocumentTraceKind = DimensionName | "consistency";

export type InspectorDocumentTraceRef =
  | {
      type: "variable";
      sectionName: string;
      variableName: string;
      dimension: DimensionName;
      grade: Grade;
      issues: string[];
      recommendation: string;
      /** Absent content, distinguished from present content graded poorly. */
      missing: boolean;
    }
  | {
      type: "section";
      sectionName: string;
      dimension: DimensionName;
      grade: Grade;
      issues: string[];
      recommendation: string;
    }
  | {
      type: "consistency";
      sections: string[];
      description: string;
      recommendation: string;
    };

export type InspectorDocumentAnnotation = DocumentAnnotation<
  InspectorDocumentTraceKind,
  InspectorDocumentTraceRef
>;

const DIMENSION_LAYER_LABEL: Record<DimensionName, string> = {
  completeness: "Completeness",
  adherence: "Template adherence",
  rigor: "Rigor",
};

/**
 * A negative result, not a system error, so this rides the tone tokens rather
 * than `--destructive`. `N/A` never reaches here — see `skipsDimension`.
 */
const GRADE_TONE: Record<Exclude<Grade, "N/A">, DocumentAnnotationEmphasis["tone"]> = {
  A: "neutral",
  B: "neutral",
  C: "caution",
  D: "danger",
  F: "danger",
};

/**
 * `N/A` means the rubric does not apply, so there is no finding to locate.
 * Emitting one would add a gutter control carrying no information.
 *
 * A predicate rather than a boolean helper so callers narrow to the grades that
 * actually have a tone, instead of asserting past the gap.
 */
function isGraded(grade: Grade): grade is Exclude<Grade, "N/A"> {
  return grade !== "N/A";
}

function emphasisFor(grade: Exclude<Grade, "N/A">): DocumentAnnotationEmphasis {
  return { tone: GRADE_TONE[grade], badge: grade };
}

function unique(values: string[]): string[] {
  return values.filter((value, index, items) => value && items.indexOf(value) === index);
}

/**
 * The last retained block of a rubric section, used to place absences.
 *
 * Last rather than first, so a gap reads after the content it is missing from.
 * Only `section_label` is consulted; falling back to `heading_stack` would give
 * two matching rules and therefore two ways to be wrong about location.
 */
function sectionAnchors(blocks: ContentBlock[]): Map<string, string> {
  const anchors = new Map<string, string>();
  const ordered = [...blocks].sort(
    (left, right) =>
      left.doc_id.localeCompare(right.doc_id) ||
      left.ordinal - right.ordinal ||
      left.id.localeCompare(right.id),
  );
  for (const block of ordered) {
    const label = block.section_label?.trim();
    if (label) anchors.set(label, block.id);
  }
  return anchors;
}

function dimensionSummary(grade: DimensionGrade, fallback: string): string {
  return grade.issues[0]?.trim() || grade.recommendation.trim() || fallback;
}

function variableAnnotations(
  section: SectionGrade,
  variable: VariableGrade,
  dimension: DimensionName,
  anchor: string | undefined,
): InspectorDocumentAnnotation[] {
  const grade = variable.dimensions[dimension];
  if (!grade || !isGraded(grade.grade)) return [];

  const missing = section.missing_variables.includes(variable.variable_name);
  const blockIds = unique(variable.block_ids);
  // One rule covers missing variables, not-applicable-but-cited content, and
  // anything else the grader left without lineage.
  const placed = blockIds.length > 0;

  return [{
    id: `inspector:${dimension}:${section.section_name}:${variable.variable_name}`,
    kind: dimension,
    layerLabel: DIMENSION_LAYER_LABEL[dimension],
    title: variable.variable_name,
    summary: dimensionSummary(
      grade,
      missing ? "Required content is not present." : "No issue recorded.",
    ),
    statusLabel: missing ? `Missing · ${grade.grade}` : grade.grade,
    blockIds: placed ? blockIds : [],
    spans: [],
    emphasis: emphasisFor(grade.grade),
    ...(placed ? {} : anchor ? { displayAnchorBlockId: anchor } : {}),
    sourceRef: {
      type: "variable",
      sectionName: section.section_name,
      variableName: variable.variable_name,
      dimension,
      grade: grade.grade,
      issues: [...grade.issues],
      recommendation: grade.recommendation,
      missing,
    },
  }];
}

/**
 * A prose section is graded as a whole and `SectionGrade` carries no block IDs,
 * so its grades can only ever be anchored.
 */
function proseSectionAnnotations(
  section: SectionGrade,
  dimension: DimensionName,
  anchor: string | undefined,
): InspectorDocumentAnnotation[] {
  const grade = section.dimensions[dimension];
  if (!grade || !isGraded(grade.grade)) return [];
  return [{
    id: `inspector:${dimension}:${section.section_name}`,
    kind: dimension,
    layerLabel: DIMENSION_LAYER_LABEL[dimension],
    title: section.section_name,
    summary: dimensionSummary(grade, "No issue recorded."),
    statusLabel: grade.grade,
    blockIds: [],
    spans: [],
    emphasis: emphasisFor(grade.grade),
    ...(anchor ? { displayAnchorBlockId: anchor } : {}),
    sourceRef: {
      type: "section",
      sectionName: section.section_name,
      dimension,
      grade: grade.grade,
      issues: [...grade.issues],
      recommendation: grade.recommendation,
    },
  }];
}

export function buildInspectorDocumentAnnotations(
  result: InspectionResult,
): InspectorDocumentAnnotation[] {
  const anchors = sectionAnchors(result.blocks ?? []);
  const annotations: InspectorDocumentAnnotation[] = [];

  for (const section of result.section_grades ?? []) {
    const anchor = anchors.get(section.section_name.trim());
    for (const dimension of DIMENSION_NAMES) {
      if (section.variable_grades.length > 0) {
        for (const variable of section.variable_grades) {
          annotations.push(...variableAnnotations(section, variable, dimension, anchor));
        }
      } else {
        annotations.push(...proseSectionAnnotations(section, dimension, anchor));
      }
    }
  }

  for (const [index, finding] of (result.cross_section_findings ?? []).entries()) {
    const blockIds = unique(finding.block_ids);
    const sections = unique(finding.sections);
    annotations.push({
      id: `inspector:consistency:${index}`,
      kind: "consistency",
      layerLabel: "Cross-section consistency",
      title: sections.length ? sections.join(" ↔ ") : "Cross-section conflict",
      summary: finding.description,
      statusLabel: "Conflict",
      blockIds,
      spans: [],
      // Two sections that cannot both hold is a negative result, always.
      emphasis: { tone: "danger", badge: "!" },
      ...(blockIds.length ? {} : anchorForSections(sections, anchors)),
      sourceRef: {
        type: "consistency",
        sections,
        description: finding.description,
        recommendation: finding.recommendation,
      },
    });
  }

  return annotations;
}

/** A conflict without lineage anchors to the first of its named sections. */
function anchorForSections(
  sections: string[],
  anchors: Map<string, string>,
): { displayAnchorBlockId?: string } {
  for (const section of sections) {
    const anchor = anchors.get(section.trim());
    if (anchor) return { displayAnchorBlockId: anchor };
  }
  return {};
}
