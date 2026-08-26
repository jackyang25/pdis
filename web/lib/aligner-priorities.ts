import type { AlignmentEdge, AlignmentFinding, AlignmentResult, AlignmentVerdict } from "./api.ts";
import { ALIGNMENT_VERDICTS, VERDICT_LABELS } from "./api.ts";
import { chainWarningText, chainWarnings } from "./aligner-chain.ts";
import type { PriorityItem } from "./priorities.ts";

/**
 * What Aligner puts at the top, how its verdicts are counted, and how they group.
 *
 * The one place each of those is decided. Nothing here re-judges anything: every
 * function reads the verdicts the result already carries, so a count, a panel and a
 * grouped list cannot disagree about the same run.
 */

/** Why this order, in the reader's words. Shown beneath the list. */
export const ALIGNER_ORDER_NOTE =
  "Wording is Aligner's. The order is not: requirements the other document falls "
  + "short of come first, then ones it addresses in terms that cannot be compared, "
  + "then ones it does not address, then ones it meets that an earlier comparison "
  + "already flagged. Each also appears under its comparison below.";

export const ALIGNER_EMPTY_MESSAGE =
  "Every requirement in the reference documents is met or exceeded.";

/**
 * Which verdicts reach the panel, in the order they appear there.
 *
 * `meets` and `exceeds` are absent because neither asks anything of anyone. `exceeds`
 * is worth a reader's attention — a candidate well past its target may mean the target
 * is stale — but that is a question about the reference document, not a shortfall in
 * the one being measured, and mixing the two would make the panel a list of two
 * different things.
 *
 * `not_addressed` comes last on purpose. Silence is the weakest signal here: many
 * requirements are addressed in documents this run never held, so an unaddressed one is
 * often a question about scope rather than a gap.
 */
const RAISED_VERDICTS: AlignmentVerdict[] = [
  "falls_short",
  "not_comparable",
  "not_addressed",
];

export function selectAlignerPriorities(result: AlignmentResult): PriorityItem[] {
  const edges = new Map(result.edges.map((edge) => [edge.edge_id, edge]));
  const raised = RAISED_VERDICTS.flatMap((verdict) =>
    result.findings
      .filter((finding) => finding.verdict === verdict)
      .map((finding) => ({
        id: finding.requirement_id,
        label: finding.requirement,
        // Which comparison raised it, because the same wording means different things
        // across two edges: a shortfall against an iTPP is a candidate question, and
        // one against a cTPP is a plan question.
        qualifier: `${VERDICT_LABELS[verdict]} · ${comparisonLabel(edges.get(finding.edge_id), result)}`,
        statement: finding.statement,
        // The gap, where there is one, is what a reader does next — so it goes in the
        // slot the panel reserves for that, rather than being appended to the
        // statement where it would read as more description.
        recommendation: finding.gap || undefined,
        // The measured document's passages, not the requirement's: the panel is about
        // what this document does, and the bar is checkable from the row below.
        blockIds: finding.comparison_block_ids,
      })),
  );

  /*
    Last: requirements the measured document meets, on a passage an earlier comparison
    left unsettled. They belong here for the reason nothing else does — they are the one
    finding a reader cannot spot by scanning. Every verdict involved reads as good news,
    and the situation they describe (a plan on track to deliver something the candidate
    already got wrong) is only visible by holding two comparisons side by side.

    Kept out of the verdict groups above rather than sorted among them: a `meets` in a
    list of shortfalls would read as a mistake, so the qualifier states both facts.
  */
  const warnings = chainWarnings(result);
  const chained = result.findings
    .filter((finding) => warnings.has(finding.requirement_id))
    .flatMap((finding) =>
      (warnings.get(finding.requirement_id) ?? []).map((warning) => ({
        // Qualified by the upstream finding, because one downstream requirement can sit
        // on two flagged passages and each is a separate thing to go and read.
        id: `${finding.requirement_id}+${warning.upstreamRequirementId}`,
        label: finding.requirement,
        qualifier: `${VERDICT_LABELS[finding.verdict]} here · flagged upstream · ${comparisonLabel(edges.get(finding.edge_id), result)}`,
        statement: finding.statement,
        recommendation: chainWarningText(warning),
        blockIds: warning.blockIds,
      })),
    );

  return [...raised, ...chained];
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
