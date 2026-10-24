/**
 * A report of one result a reader believes is wrong, sent as an email the reader writes.
 *
 * PDIS keeps no server state, so a report leaves through the reader's own mail client;
 * what a pilot needs is for the complaint to arrive with enough to find the finding
 * again - which tool, which finding, its own words, where it points in the document.
 * Building that by hand is where reports lose the detail that makes them actionable.
 */

/** Where feedback goes. Named once: the header's feedback panel uses it too. */
export const FEEDBACK_EMAIL = "jack.yang@gatesfoundation.org";

export function feedbackMailto(subject: string, body = ""): string {
  const query = [`subject=${encodeURIComponent(subject)}`, body && `body=${encodeURIComponent(body)}`];
  return `mailto:${FEEDBACK_EMAIL}?${query.filter(Boolean).join("&")}`;
}

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

export function findingReportMailto(report: FindingReport): string {
  return feedbackMailto(`PDIS finding report: ${report.tool}`, findingReportText(report));
}
