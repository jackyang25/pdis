/**
 * Production release history, newest first. The first three versions were assigned
 * retrospectively to confirmed promotions. The owner supplied Eastern-time dates.
 * One entry per distinct release, not per build or redeployment. Pending work stays
 * separate. See docs/deployment.md for the release checklist.
 */
type Release = {
  version: string;
  releasedAt: string;
  productionBuild: number;
  title: string;
  changes: readonly string[];
};

export const RELEASES: readonly Release[] = [
  {
    version: "0.2.1",
    releasedAt: "2026-09-14T16:31:00-04:00",
    productionBuild: 33,
    title: "Scout evidence refinements",
    changes: [
      "Clarified how Scout distinguishes conflicting evidence from differences between products or target specifications.",
      "Updated how Scout selects document targets for evidence review.",
    ],
  },
  {
    version: "0.2.0",
    releasedAt: "2026-09-14T14:10:00-04:00",
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
    releasedAt: "2026-09-03T00:17:00-04:00",
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
  "Scout result compatibility: after this update is deployed, run Scout again to generate a compatible result. Previously exported Scout files cannot be imported into the updated version.",
  "Improved Scout numeric target extraction and independent AI review, with more source context and more specific recommendation reasons.",
  "Scout now distinguishes unclear source text, failed extraction, and unavailable AI review, so you can see what needs attention and which decisions remain available.",
  "Simplified Scout review navigation and decision controls. Recorded decisions remain editable before continuing, and source passages and comparison qualifiers are available for inspection.",
  "Clarified Scout help: the first checkpoint reviews numeric document targets; the second reviews external measurements against those targets.",
  "Improved Scout number formatting, including calendar years and singular or plural units such as 2027, 1 dose, and 2 doses.",
  "Assistant can explain the active Scout review and its sources without changing review decisions.",
  "Added a shared reminder to verify AI-generated results against their sources.",
  "Added release notes and Teams contact guidance for feedback and requests in the header.",
];

export function formatReleaseDate(value: string): string {
  return new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
  }).format(new Date(value));
}
