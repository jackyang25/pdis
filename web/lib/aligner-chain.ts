import { spanBlockIds } from "./api.ts";
import type { AlignmentFinding, AlignmentResult, AlignmentVerdict } from "./api.ts";

/**
 * Where two comparisons meet, and what one of them knows that the other cannot.
 *
 * A run with three documents makes two comparisons, and the middle document is in both:
 * measured against the first, authoritative over the third. So a plan can faithfully
 * deliver a commitment that itself falls short of the profile, and every verdict
 * involved is correct — the plan really does meet the cTPP. Read the second comparison
 * alone and it is all good news.
 *
 * Nothing here re-judges that. It links the two findings that already describe the
 * situation and lets the view say so once.
 *
 * The join is a block id. The middle document is the only document both comparisons
 * touch, so it is the only place they can meet: the upstream finding cites the passage
 * where the commitment falls short, and the downstream requirement cites the passage
 * that states the commitment. The same id on both sides is the same passage.
 *
 * Its one weakness, and the reason the wording matters: a block is a paragraph or a
 * table row, and a dense one can carry several facts. Two findings can cite it about
 * different things. So a warning is a claim about the **passage**, never a claim that
 * the two requirements are the same one — which is true whether the block holds one
 * fact or four, and still sends a reader to the right place. Matching requirement text
 * instead would be fuzzy string comparison, which this codebase refuses everywhere else.
 */

/**
 * Verdicts that leave a requirement unestablished against its bar.
 *
 * Exactly the two shortfalls. `not_addressed` cannot appear here even in
 * principle: it cites no passage, so there is nothing for a later comparison to join to.
 */
const UNSETTLED: AlignmentVerdict[] = ["falls_short", "not_comparable"];

/**
 * Verdicts worth warning about downstream.
 *
 * Only the two that read as good news. A downstream `falls_short` is already in the
 * priorities and already states its own shortfall, so flagging it again would put one
 * requirement in the panel twice for two different reasons.
 */
const SILENT_ABOUT_IT: AlignmentVerdict[] = ["meets", "exceeds"];

export type ChainWarning = {
  /** The downstream finding this warns about. */
  requirementId: string;
  /**
   * The upstream findings that know better, so a reader can go and read them.
   *
   * A list because a passage can be cited by several. One warning used to be made per
   * upstream finding, which contradicted the claim it renders: the sentence says *this
   * passage* also falls short, and says nothing about which upstream requirement said
   * so. Four upstream findings over one passage therefore drew four lines carrying two
   * distinct sentences, two of them exact duplicates of the others.
   *
   * The claim decides the key. A warning is one passage against one bar under one
   * verdict, and everything that reached it is recorded here.
   */
  upstreamRequirementIds: string[];
  /** Its verdict on the shared passage — `falls_short` or `not_comparable`. */
  upstreamVerdict: AlignmentVerdict;
  /** The document that sets the bar the shared passage falls short of. */
  upstreamReference: string;
  /** The document holding the shared passage. */
  sharedDocument: string;
  /** The passages both comparisons cite. */
  blockIds: string[];
};

/**
 * Every downstream finding that delivers something an earlier comparison flagged.
 *
 * Keyed by the downstream finding's requirement id. General over whatever chain the
 * configuration declares: an upstream comparison is any edge whose measured document is
 * this edge's reference document, so a fourth document type with an edge joins the chain
 * without this function changing.
 */
export function chainWarnings(
  result: AlignmentResult,
): Map<string, ChainWarning[]> {
  const names = new Map(
    result.documents.map((document) => [
      document.doc_id,
      document.display_name || document.source_type || document.doc_id,
    ]),
  );
  const findingsByEdge = new Map<string, AlignmentFinding[]>();
  for (const finding of result.findings) {
    const held = findingsByEdge.get(finding.edge_id) ?? [];
    held.push(finding);
    findingsByEdge.set(finding.edge_id, held);
  }

  const warnings = new Map<string, ChainWarning[]>();
  for (const edge of result.edges) {
    // The comparisons that measured this edge's reference document. Read from the
    // edges the run made, so nothing here names a document type.
    const upstream = result.edges.filter(
      (other) =>
        other.edge_id !== edge.edge_id
        && other.comparison_doc_id === edge.reference_doc_id,
    );
    if (upstream.length === 0) continue;

    // Which passages of the shared document an earlier comparison left unsettled.
    const unsettledByBlock = new Map<string, AlignmentFinding[]>();
    for (const other of upstream) {
      for (const finding of findingsByEdge.get(other.edge_id) ?? []) {
        if (!UNSETTLED.includes(finding.verdict)) continue;
        for (const blockId of spanBlockIds(finding.comparison_spans)) {
          const held = unsettledByBlock.get(blockId) ?? [];
          held.push(finding);
          unsettledByBlock.set(blockId, held);
        }
      }
    }
    if (unsettledByBlock.size === 0) continue;

    for (const finding of findingsByEdge.get(edge.edge_id) ?? []) {
      if (!SILENT_ABOUT_IT.includes(finding.verdict)) continue;
      // Keyed by the claim the reader is shown: one bar, one verdict. Keying by the
      // upstream requirement instead produced one line per upstream finding, and since
      // the sentence names neither the requirement nor anything else that varies, the
      // extra lines were literally the same words repeated.
      const byClaim = new Map<string, ChainWarning>();
      for (const blockId of spanBlockIds(finding.reference_spans)) {
        for (const earlier of unsettledByBlock.get(blockId) ?? []) {
          const upstreamEdge = result.edges.find(
            (item) => item.edge_id === earlier.edge_id,
          );
          const upstreamReference = upstreamEdge
            ? names.get(upstreamEdge.reference_doc_id) ?? upstreamEdge.reference_doc_id
            : "";
          const key = `${earlier.verdict}\u241f${upstreamReference}`;
          const existing = byClaim.get(key);
          if (existing) {
            if (!existing.blockIds.includes(blockId)) existing.blockIds.push(blockId);
            if (!existing.upstreamRequirementIds.includes(earlier.requirement_id)) {
              existing.upstreamRequirementIds.push(earlier.requirement_id);
            }
            continue;
          }
          byClaim.set(key, {
            requirementId: finding.requirement_id,
            upstreamRequirementIds: [earlier.requirement_id],
            upstreamVerdict: earlier.verdict,
            upstreamReference,
            sharedDocument:
              names.get(edge.reference_doc_id) ?? edge.reference_doc_id,
            blockIds: [blockId],
          });
        }
      }
      if (byClaim.size > 0) {
        warnings.set(finding.requirement_id, [...byClaim.values()]);
      }
    }
  }
  return warnings;
}

/**
 * One warning as a reader should see it.
 *
 * A claim about the passage, deliberately: "this passage also falls short" is true
 * however many facts the passage holds, where "this requirement falls short" would be
 * asserting the two comparisons are about the same one.
 *
 * It quoted the upstream finding's `gap` sentence, which no longer exists: that sentence
 * restated the upstream requirement, and a reader following this warning arrives at the
 * upstream finding where the requirement is the heading. The warning's job is to say
 * there is something to follow, not to summarise it here.
 */
export function chainWarningText(warning: ChainWarning): string {
  const many = warning.blockIds.length > 1;
  const verdict =
    warning.upstreamVerdict === "falls_short"
      ? `${many ? "fall" : "falls"} short of the ${warning.upstreamReference}`
      : `cannot be compared with the ${warning.upstreamReference}`;
  const subject = many
    ? `These ${warning.blockIds.length} passages of the ${warning.sharedDocument}`
    : `This passage of the ${warning.sharedDocument}`;
  return `${subject} also ${verdict}.`;
}
