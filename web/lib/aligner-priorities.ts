import type { AlignmentEdge, AlignmentFinding, AlignmentResult, AlignmentVerdict } from "./api.ts";
import { displayLabel } from "./display-label.ts";
import { ALIGNMENT_VERDICTS, VERDICT_LABELS, alignmentBlockIds } from "./api.ts";
import { chainWarningText, chainWarnings } from "./aligner-chain.ts";
import type { PriorityFinding } from "./priorities.ts";

/**
 * How Aligner's verdicts are counted, how they group, and how its result is read for the
 * priority card.
 *
 * The one place each of those is decided. Nothing here re-judges anything: every function
 * reads the verdicts the result already carries, so a count, a card and a grouped list
 * cannot disagree about the same run.
 */

export const ALIGNER_PRIORITY_FOCUS =
  "Requirements the measured document falls short of or states in terms that cannot be "
  + "compared, then ones it does not address, and any it meets on a passage an earlier "
  + "comparison flagged.";

/**
 * One finding per requirement, every verdict included.
 *
 * A requirement met on a passage an earlier comparison left unsettled carries that as a
 * note. It is the one situation no single verdict shows - every verdict involved reads as
 * good news - and it is derived by code from shared block ids, so it travels as a note rather
 * than as anything a model wrote.
 */
export function alignerPriorityFindings(result: AlignmentResult): PriorityFinding[] {
  const edges = new Map(result.edges.map((edge) => [edge.edge_id, edge]));
  const warnings = chainWarnings(result);
  return result.findings.map((finding) => {
    const chained = warnings.get(finding.requirement_id) ?? [];
    return {
      id: finding.requirement_id,
      subject: finding.requirement,
      // Which comparison judged it, because the same wording means different things across
      // two: a shortfall against an iTPP is a candidate question, one against a cTPP a plan
      // question.
      group: comparisonLabel(edges.get(finding.edge_id), result),
      verdicts: [VERDICT_LABELS[finding.verdict]],
      statements: [finding.statement],
      notes: chained.map(chainWarningText),
      // The measured document's passages, and the shared passage of any chained warning:
      // the card is about what this document does, and the bar is in the row below.
      blockIds: [
        ...new Set([
          ...alignmentBlockIds(finding, "comparison"),
          ...chained.flatMap((warning) => warning.blockIds),
        ]),
      ],
    };
  });
}

/** How many findings landed on each verdict. Derived, never stored. */
export function countVerdicts(
  result: AlignmentResult,
): Record<AlignmentVerdict, number> {
  const counts = Object.fromEntries(
    ALIGNMENT_VERDICTS.map((verdict) => [verdict, 0]),
  ) as Record<AlignmentVerdict, number>;
  for (const finding of result.findings) counts[finding.verdict] += 1;
  return counts;
}

/**
 * Findings grouped by the comparison that produced them, in the order the run made
 * them, each group keeping the order its requirements were read in.
 *
 * By comparison and nothing else. Grouping by verdict as well would put one requirement
 * in two places, and grouping by the reference document's sections would invent a
 * hierarchy out of whatever headings that document happened to use.
 */
export function findingsByComparison(
  result: AlignmentResult,
): { edge: AlignmentEdge; findings: AlignmentFinding[] }[] {
  return result.edges.map((edge) => ({
    edge,
    findings: result.findings.filter((finding) => finding.edge_id === edge.edge_id),
  }));
}

/** Findings on one comparison carrying one verdict, in the order they were read. */
export function findingsWithVerdict(
  findings: AlignmentFinding[],
  verdict: AlignmentVerdict,
): AlignmentFinding[] {
  return findings.filter((finding) => finding.verdict === verdict);
}

/**
 * How a comparison reads in one line: which document sets the bar, which is measured.
 *
 * Document types rather than filenames, because the type is what a reader recognises
 * and what the configuration declares. Falls back to the document id for a type the
 * result carries but the run's documents do not name.
 */
export function comparisonLabel(
  edge: AlignmentEdge | undefined,
  result: AlignmentResult,
): string {
  if (!edge) return "";
  return `${documentName(edge.reference_doc_id, result)} → ${documentName(edge.comparison_doc_id, result)}`;
}

export function documentName(docId: string, result: AlignmentResult): string {
  const document = result.documents.find((item) => item.doc_id === docId);
  return document?.display_name || document?.source_type || docId;
}

/**
 * The document's type, for a label that only has to tell two sides apart.
 *
 * `documentName` gives the file's own title - "Vaccine Intervention TPP" - which is what
 * identifies a document and belongs where a reader first meets it: the comparison card's
 * heading, the trace, the run history. Repeated as a row label it was two hundred pixels
 * of every row, fifty-three times, saying what the heading two lines up had already said.
 *
 * A row label has a smaller job. The heading has already bound each side to a document,
 * so the label only has to say which side this line is, and the shortest thing that does
 * that is the type. A run cannot hold two documents of one type - `resolve_edges` refuses
 * it - so the type is unambiguous within a comparison.
 */
export function documentType(docId: string, result: AlignmentResult): string {
  const document = result.documents.find((item) => item.doc_id === docId);
  return displayLabel(document?.source_type || docId);
}
