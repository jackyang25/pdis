/**
 * Production release history, newest first. The first three versions were assigned
 * retrospectively to confirmed promotions. Dates are authored calendar dates,
 * not deployment completion timestamps.
 * One entry per distinct release, not per build or redeployment. Pending work stays
 * separate. See docs/deployment.md for the release checklist.
 */
type Release = {
  version: string;
  releasedOn: string;
  productionBuild?: number;
  title: string;
  changes: readonly string[];
};

export const RELEASES: readonly Release[] = [
  {
    version: "0.2.1",
    releasedOn: "2026-09-14",
    productionBuild: 33,
    title: "Scout evidence refinements",
    changes: [
      "Clarified how Scout distinguishes conflicting evidence from differences between products or target specifications.",
      "Updated the model used to extract Scout’s document targets.",
    ],
  },
  {
    version: "0.2.0",
    releasedOn: "2026-09-14",
    productionBuild: 30,
    title: "Broader reviews and document coverage",
    changes: [
      "Inspector can review one document against multiple applicable rubrics, with separate results and visible rubric revisions.",
      "Improved Scout’s IPDP claim extraction, duplicate-claim reconciliation, and evidence review panels.",
      "Screener now reads directly embedded images in text-based PDFs and explains the format’s extraction limitations.",
      "Made document traces, citations, result layouts, and progress messages more consistent across tools.",
      "Added Female Contraception to the indication list.",
    ],
  },
  {
    version: "0.1.0",
    releasedOn: "2026-09-03",
    productionBuild: 13,
    title: "Initial production release",
    changes: [
      "Introduced the PDIS workspace for document review, evidence checks, and stage-gate screening.",
      "Connected the production evidence-retrieval service.",
    ],
  },
];

export const CURRENT_RELEASE = RELEASES[0];

export const UNRELEASED_CHANGES: readonly string[] = [
  "Scout compatibility: after this update is deployed, rerun Scout to create a compatible result. Previously exported Scout files cannot be imported into the updated version.",
  "Improved Scout numeric target extraction and AI review with more source context, clearer recommendation reasons, and distinct notices for uncertainty and processing failures.",
  "Simplified Scout’s two review checkpoints with editable decisions, clearer help, and inspectable source passages and comparison qualifiers.",
  "Improved Scout number formatting for calendar years and singular or plural units, such as 2027, 1 dose, and 2 doses.",
  "Assistant can explain the active Scout review and its sources without changing review decisions.",
  "Refined the tool catalog and added release notes, Teams feedback contacts, and a shared reminder to verify AI-generated results against their sources.",
];

export function formatReleaseDate(value: string): string {
  return new Intl.DateTimeFormat("en-US", {
    // Date-only ISO values parse at UTC midnight; keep their authored day.
    timeZone: "UTC",
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(new Date(value));
}
