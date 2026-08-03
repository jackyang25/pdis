import type {
  ContentStatus,
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
      /** The presence answer, so a placeholder is not reported as a gap. */
      contentStatus: ContentStatus;
      /** Convenience for the common branch; `contentStatus` is the authority. */
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
 * Where an absence is displayed: the end of the section it belongs to.
 *
 * Reads the section's published `mapped_block_ids` - the same mapping the grader
 * used to build the prompt - so nothing here re-derives a section from
 * `section_label`. The document is rendered in ordinal order, so the section's
 * end is its highest-ordinal block. Taking the maximum rather than the last item
 * means the list's own sequence does not matter, which is one fewer thing that
 * has to stay true. Last rather than first, so a gap reads after the content it
 * is missing from.
 */
function sectionAnchor(
  section: SectionGrade,
  ordinalById: Map<string, number>,
): string | undefined {
  let anchor: string | undefined;
  let highest = -Infinity;
  for (const blockId of section.mapped_block_ids) {
    const ordinal = ordinalById.get(blockId);
    if (ordinal === undefined || ordinal < highest) continue;
    highest = ordinal;
    anchor = blockId;
  }
  return anchor;
}

/** Presence is the headline when content is absent or only a placeholder. */
const CONTENT_STATUS_LABEL: Partial<Record<ContentStatus, string>> = {
  missing: "Not present",
  placeholder: "Placeholder",
  partial: "Partially filled",
};

function statusLabelFor(status: ContentStatus, grade: Grade): string {
  const presence = CONTENT_STATUS_LABEL[status];
  return presence ? `${presence} · ${grade}` : grade;
}

function dimensionSummary(grade: DimensionGrade, fallback: string): string {
  // Only an issue can be the summary. Falling through to the recommendation
  // made a clean grade read "None." — the model's way of saying there is
  // nothing to recommend, shown as though it were the finding.
  return grade.issues[0]?.trim() || fallback;
}

function variableAnnotations(
  section: SectionGrade,
  variable: VariableGrade,
  dimension: DimensionName,
  anchor: string | undefined,
): InspectorDocumentAnnotation[] {
  const grade = variable.dimensions[dimension];
  if (!grade || !isGraded(grade.grade)) return [];

  const missing = variable.content_status === "missing";
  // This dimension's own citations. Each dimension judges and cites
  // independently, so a completeness verdict is never placed on a block only
  // rigor read.
  const blockIds = unique(grade.cited_block_ids);
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
    statusLabel: statusLabelFor(variable.content_status, grade.grade),
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
      contentStatus: variable.content_status,
      missing,
    },
  }];
}

/**
 * A prose section is graded as a whole rather than per variable, so its scope is
 * every block the section mapper assigned to it.
 *
 * That scope is lineage, not absence. Treating it as absence made a section that
 * exists and scores `A` render under "not present in the document". A section
 * that genuinely is not present maps no blocks, so the same rule anchors it —
 * one rule, both cases, matching how variables are placed.
 */
function proseSectionAnnotations(
  section: SectionGrade,
  dimension: DimensionName,
  anchor: string | undefined,
): InspectorDocumentAnnotation[] {
  const grade = section.dimensions[dimension];
  if (!grade || !isGraded(grade.grade)) return [];
  const blockIds = unique(section.mapped_block_ids);
  const placed = blockIds.length > 0;
  return [{
    id: `inspector:${dimension}:${section.section_name}`,
    kind: dimension,
    layerLabel: DIMENSION_LAYER_LABEL[dimension],
    title: section.section_name,
    summary: dimensionSummary(grade, "No issue recorded."),
    statusLabel: grade.grade,
    blockIds: placed ? blockIds : [],
    spans: [],
    emphasis: emphasisFor(grade.grade),
    ...(placed ? {} : anchor ? { displayAnchorBlockId: anchor } : {}),
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
  const annotations: InspectorDocumentAnnotation[] = [];
  const ordinalById = new Map(
    (result.blocks ?? []).map((block) => [block.id, block.ordinal]),
  );
  const anchorBySection = new Map(
    (result.section_grades ?? []).map((section) => [
      section.section_name,
      sectionAnchor(section, ordinalById),
    ]),
  );

  for (const section of result.section_grades ?? []) {
    const anchor = anchorBySection.get(section.section_name);
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
      ...(blockIds.length ? {} : anchorForSections(sections, anchorBySection)),
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
  anchorBySection: Map<string, string | undefined>,
): { displayAnchorBlockId?: string } {
  for (const section of sections) {
    const anchor = anchorBySection.get(section);
    if (anchor) return { displayAnchorBlockId: anchor };
  }
  return {};
}
