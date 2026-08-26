import type {
  Assessment,
  InspectionResult,
  SectionAssessment,
  Verdict,
} from "./api.ts";
import { VERDICT_LABEL, worklist } from "./api.ts";
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
 * One annotation per unit that needs work, because a unit is already one thing to
 * fix. The shape this replaced looped three dimensions over every unit and branched
 * on whether a section had variables, so one defect could produce three gutter
 * markers and two of the three were usually empty.
 *
 * Inspector carries no exact quotes, only block ids, so annotations claim whole
 * blocks rather than spans. Synthesizing a span by searching block text for a
 * variable name would invent provenance the model never asserted.
 */

export type InspectorDocumentTraceKind = Verdict;

export type InspectorDocumentTraceRef = {
  /** The unit's own id, which is also what the row's trigger sends. */
  assessmentId: string;
  verdict: Verdict;
  statement: string;
  sectionName: string | null;
  variableName: string | null;
};

export type InspectorDocumentAnnotation = DocumentAnnotation<
  InspectorDocumentTraceKind,
  InspectorDocumentTraceRef
>;

/**
 * A negative result, not a system error, so this rides the tone tokens rather
 * than `--destructive`.
 *
 * Read from the vocabulary's own order, which is declared worst-first: the verdicts
 * that leave something absent read as danger, and the one that leaves the requirement
 * covered but unusable reads as caution. There is no separate tone table to keep in step, and no
 * severity field - the position in the one list is the severity.
 */
const WEAKER_VERDICTS: readonly Verdict[] = ["vague"];

function emphasisFor(item: Assessment): DocumentAnnotationEmphasis {
  return {
    tone: WEAKER_VERDICTS.includes(item.verdict) ? "caution" : "danger",
    badge: VERDICT_LABEL[item.verdict] ?? item.verdict,
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
  item: Assessment,
  sectionByBlock: Map<string, string>,
): string {
  if (item.variable_name) return item.variable_name;
  if (item.section_name) return item.section_name;
  // A conflict belongs to no single section, so it is titled by the sections its
  // own citations resolve to - the same derivation the result relies on.
  const sections = unique(
    item.cited_block_ids.map((blockId) => sectionByBlock.get(blockId) ?? ""),
  );
  return sections.length ? sections.join(" ↔ ") : "Cross-section conflict";
}

/**
 * The annotation ID a finding gets in the trace.
 *
 * Exported because the unit rows send readers here, and a trigger that names the wrong
 * ID falls back to every layer without saying so. Built in one place so the two sides
 * cannot spell it differently.
 */
export function inspectorAnnotationId(assessmentId: string): string {
  return `inspector:${assessmentId}`;
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
  // The same list the fix list shows, so the gutter and the list can never
  // disagree about what counts as work. Units the rubric marks optional and
  // absent are excluded by that one rule rather than a second one repeated here.
  return worklist(result).map((item) => {
    const blockIds = unique(item.cited_block_ids);
    const anchor = item.section_name
      ? anchorBySection.get(item.section_name)
      : conflictAnchor(item, sectionByBlock, anchorBySection);
    const label = VERDICT_LABEL[item.verdict] ?? item.verdict;

    return {
      id: inspectorAnnotationId(item.id),
      kind: item.verdict,
      layerLabel: label,
      title: titleFor(item, sectionByBlock),
      summary: item.statement,
      statusLabel: label,
      blockIds,
      spans: [],
      emphasis: emphasisFor(item),
      ...(blockIds.length || !anchor ? {} : { displayAnchorBlockId: anchor }),
      // No unit status beside the verdict. It used to carry both, because the unit
      // wore a status while the finding on it wore a reason; they are one field now.
      sourceRef: {
        assessmentId: item.id,
        verdict: item.verdict,
        statement: item.statement,
        sectionName: item.section_name,
        variableName: item.variable_name,
      },
    };
  });
}

/** A conflict without lineage anchors to the first section it can resolve. */
function conflictAnchor(
  item: Assessment,
  sectionByBlock: Map<string, string>,
  anchorBySection: Map<string, string | undefined>,
): string | undefined {
  for (const blockId of item.cited_block_ids) {
    const section = sectionByBlock.get(blockId);
    if (!section) continue;
    const anchor = anchorBySection.get(section);
    if (anchor) return anchor;
  }
  return undefined;
}
