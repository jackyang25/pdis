/**
 * Product versions bundled with this code, newest first—not deployment records.
 * Assign a version to a coherent, ready set of changes. Deployments can include
 * several entries; rebuilding or deploying later does not change these notes.
 * See docs/deployment.md. Historical deployment dates remain in Git history.
 */
type Release = {
  version: string;
  title: string;
  sections: readonly {
    /** Short releases need no extra heading. */
    title?: string;
    changes: readonly string[];
  }[];
};

export const RELEASES: readonly Release[] = [
  {
    version: "0.3.0",
    title: "Clearer evidence review and document coverage",
    sections: [
      {
        title: "Saved results",
        changes: [
          "Rerun Scout to create results compatible with this version; Scout exports from earlier versions cannot be imported.",
          "Rerun original documents to benefit from improved extraction. Imported results retain their original source content; compatible older Aligner results keep their citations.",
        ],
      },
      {
        title: "Scout",
        changes: [
          "Improved numeric target extraction and independent AI review with more source context and clearer reasons for recommendations, uncertainty, and processing failures.",
          "Clarified comparison rules: evidence must measure the relevant outcome under comparable conditions, but its value need not meet the target to be compared.",
          "Simplified both review checkpoints, with editable decisions, clearer source links and comparison details, and consistent formatting for years and units.",
          "Assistant can explain the active review and its sources without changing review decisions.",
        ],
      },
      {
        title: "Document support",
        changes: [
          "Expanded DOCX extraction coverage and retained full-slide visuals for PPTX analysis. Screener now retains rendered PDF pages alongside extracted text.",
          "Kept visual references distinct from exact text quotations, with larger image views and clearer notices identifying visuals that could not be captured.",
          "Fixed section mapping for large documents that exceeded structured-output limits while preserving document context.",
        ],
      },
      {
        title: "Workspace",
        changes: [
          "Active analyses and elapsed timers remain visible when returning to a tool, even when an earlier result is selected.",
          "Tool cards show when an analysis is waiting for capacity, running, ready for review, or has results available.",
          "Refined the tool catalog, review guidance, and source presentation; added release notes, Teams feedback contacts, and a reminder to verify AI-generated results.",
        ],
      },
    ],
  },
  {
    version: "0.2.1",
    title: "Scout evidence refinements",
    sections: [{ changes: [
      "Clarified how Scout distinguishes conflicting evidence from differences between products or target specifications.",
      "Updated the model used to extract Scout’s document targets.",
    ] }],
  },
  {
    version: "0.2.0",
    title: "Broader reviews and document coverage",
    sections: [{ changes: [
      "Inspector can review one document against multiple applicable rubrics, with separate results and visible rubric revisions.",
      "Improved Scout’s IPDP claim extraction, duplicate-claim reconciliation, and evidence review panels.",
      "Screener now reads directly embedded images in text-based PDFs and explains the format’s extraction limitations.",
      "Made document traces, citations, result layouts, and progress messages more consistent across tools.",
      "Added Female Contraception to the indication list.",
    ] }],
  },
  {
    version: "0.1.0",
    title: "Initial production release",
    sections: [{ changes: [
      "Introduced the PDIS workspace for document review, evidence checks, and stage-gate screening.",
      "Connected the production evidence-retrieval service.",
    ] }],
  },
];

export const CURRENT_RELEASE = RELEASES[0];
