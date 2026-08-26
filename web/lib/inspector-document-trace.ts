import type {
  FindingReason,
  InspectionResult,
  RubricFinding,
  SectionAssessment,
  UnitStatus,
} from "./api.ts";
import { REASON_LABELS, worklist } from "./api.ts";
import type {
  DocumentAnnotation,
  DocumentAnnotationEmphasis,
} from "./document-trace.ts";

/**
 * Projects an existing `InspectionResult` into shared document annotations.
 *
 * Pure and order-preserving. It selects, labels, and places findings the result
 * already carries; it never re-assesses, re-parses prose, or infers lineage the
 * result does not already hold.
 *
 * One annotation per finding, because a finding is already one thing to fix. The
 * shape this replaced looped three dimensions over every unit and branched on
 * whether a section had variables, so one defect could produce three gutter
 * markers and two of the three were usually empty.
 *
 * Inspector carries no exact quotes, only block ids, so annotations claim whole
 * blocks rather than spans. Synthesizing a span by searching block text for a
 * variable name would invent provenance the model never asserted.
 */

export type InspectorDocumentTraceKind = FindingReason;

export type InspectorDocumentTraceRef = {
  findingId: string;
  reason: FindingReason;
  statement: string;
  recommendation: string;
  sectionName: string | null;
  variableName: string | null;
  /** The status of the unit this finding sits on; absent for a conflict. */
  status: UnitStatus | null;
};

export type InspectorDocumentAnnotation = DocumentAnnotation<
  InspectorDocumentTraceKind,
  InspectorDocumentTraceRef
>;

/**
 * A negative result, not a system error, so this rides the tone tokens rather
 * than `--destructive`.
 *
 * Derived from the finding's own level: a reason that leaves the requirement
 * unsatisfied reads as danger, one that only makes it weaker reads as caution.
 * There is no separate tone table to keep in step with the vocabulary.
 */
function emphasisFor(finding: RubricFinding): DocumentAnnotationEmphasis {
  return {
    tone: finding.level === "not_met" ? "danger" : "caution",
    badge: REASON_LABELS[finding.reason] ?? finding.reason,
  };
}

function unique(values: string[]): string[] {
  return values.filter((value, index, items) => value && items.indexOf(value) === index);
}

/**
 * Where a finding without lineage is displayed: the end of its section.
 *
 * Reads the published `mapped_block_ids` - the same mapping the assessor used to
 * build the prompt - so nothing here re-derives a section from `section_label`.
 * The document renders in ordinal order, so the section's end is its
 * highest-ordinal block. Taking the maximum rather than the last item means the
 * list's own sequence does not matter, which is one fewer thing that has to stay
 * true. Last rather than first, so an absence reads after the content it is
 * missing from.
 */
function sectionAnchor(
  section: SectionAssessment,
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

function titleFor(
  finding: RubricFinding,
  sectionByBlock: Map<string, string>,
): string {
  if (finding.variable_name) return finding.variable_name;
  if (finding.section_name) return finding.section_name;
  // A conflict belongs to no single section, so it is titled by the sections its
  // own citations resolve to - the same derivation the result relies on.
  const sections = unique(
    finding.cited_block_ids.map((blockId) => sectionByBlock.get(blockId) ?? ""),
  );
  return sections.length ? sections.join(" ↔ ") : "Cross-section conflict";
}

/**
 * The annotation ID a finding gets in the trace.
 *
 * Exported because the finding rows send readers here, and a trigger that names the wrong
 * ID falls back to every layer without saying so. Built in one place so the two sides
 * cannot spell it differently.
 */
export function inspectorAnnotationId(findingId: string): string {
  return `inspector:${findingId}`;
}

export function buildInspectorDocumentAnnotations(
  result: InspectionResult,
): InspectorDocumentAnnotation[] {
  const ordinalById = new Map(
    (result.blocks ?? []).map((block) => [block.id, block.ordinal]),
  );
  const sections = result.sections ?? [];
  const anchorBySection = new Map(
    sections.map((section) => [
      section.section_name,
      sectionAnchor(section, ordinalById),
    ]),
  );
  const sectionByBlock = new Map(
    sections.flatMap((section) =>
      section.mapped_block_ids.map(
        (blockId) => [blockId, section.section_name] as const,
      ),
    ),
  );
  const statusByUnit = new Map(
    sections.flatMap((section) =>
      section.units.map(
        (unit) =>
          [
            `${section.section_name} ${unit.variable_name ?? ""}`,
            unit.status,
          ] as const,
      ),
    ),
  );

  // The same list the fix list shows, so the gutter and the list can never
  // disagree about what counts as work. Units the rubric marks optional and
  // absent are excluded by that one rule rather than a second one repeated here.
  return worklist(result).map((finding) => {
    const blockIds = unique(finding.cited_block_ids);
    const anchor = finding.section_name
      ? anchorBySection.get(finding.section_name)
      : conflictAnchor(finding, sectionByBlock, anchorBySection);

    return {
      id: inspectorAnnotationId(finding.id),
      kind: finding.reason,
      layerLabel: REASON_LABELS[finding.reason] ?? finding.reason,
      title: titleFor(finding, sectionByBlock),
      summary: finding.statement,
      statusLabel: REASON_LABELS[finding.reason] ?? finding.reason,
      blockIds,
      spans: [],
      emphasis: emphasisFor(finding),
      ...(blockIds.length || !anchor ? {} : { displayAnchorBlockId: anchor }),
      sourceRef: {
        findingId: finding.id,
        reason: finding.reason,
        statement: finding.statement,
        recommendation: finding.recommendation,
        sectionName: finding.section_name,
        variableName: finding.variable_name,
        status:
          statusByUnit.get(
            `${finding.section_name ?? ""} ${finding.variable_name ?? ""}`,
          ) ?? null,
      },
    };
  });
}

/** A conflict without lineage anchors to the first section it can resolve. */
function conflictAnchor(
  finding: RubricFinding,
  sectionByBlock: Map<string, string>,
  anchorBySection: Map<string, string | undefined>,
): string | undefined {
  for (const blockId of finding.cited_block_ids) {
    const section = sectionByBlock.get(blockId);
    if (!section) continue;
    const anchor = anchorBySection.get(section);
    if (anchor) return anchor;
  }
  return undefined;
}
