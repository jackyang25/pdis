/**
 * A report of one result a reader believes is wrong, written for pasting into Teams.
 *
 * PDIS keeps no server state, so there is nowhere to send a report to; what a pilot needs
 * is for the reader's complaint to arrive with enough to find the finding again - which
 * tool, which finding, its own words, where it points in the document. Building that by
 * hand is where reports lose the detail that makes them actionable.
 */

/** Who reads feedback. Named once: the header's feedback panel says the same. */
export const FEEDBACK_CONTACTS = "Jack Yang or Shyam Bhaskaran";

export type FindingReport = {
  /** The tool the reader is in, as its catalog names it. */
  tool: string;
  /** What the finding is: its kind and title, as the reader sees them. */
  finding: string;
  /** The finding's own text - a model's statement, a suggestion. */
  detail?: string;
  /** A stable reference the team can search a saved result for. */
  reference?: string;
  /** Where it points: document passages, sources. */
  location?: string;
  /** What the reader says is wrong. */
  note?: string;
};

export function findingReportText(report: FindingReport): string {
  return [
    "PDIS finding report",
    `Tool: ${report.tool}`,
    `Finding: ${report.finding}`,
    report.detail?.trim() && `Text: ${report.detail.trim()}`,
    report.reference?.trim() && `Reference: ${report.reference.trim()}`,
    report.location?.trim() && `Where: ${report.location.trim()}`,
    `What is wrong: ${report.note?.trim() || "(not stated)"}`,
  ].filter(Boolean).join("\n");
}
