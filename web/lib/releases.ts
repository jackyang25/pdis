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
    version: "0.5.0",
    title: "A more focused Assistant and a refreshed workspace",
    sections: [{ changes: [
      "Assistant handles large documents and long conversations more reliably, and looks at slide visuals only when a question needs them.",
      "Assistant asks which run or document you mean when a question is unclear, and keeps different files that share a name apart.",
      "Two analyses can now run at the same time.",
      "Refreshed the look of the workspace and the feedback panel.",
    ] }],
  },
  {
    version: "0.4.1",
    title: "Streamlined screening and clearer review steps",
    sections: [{ changes: [
      "Screener picks the relevant passages from each document before assessing a question, keeping every original citation.",
      "Screener shows its progress while selecting evidence and labels required and anticipatory questions more clearly.",
      "Screener results are titled by stage gate, and downloads use short, tool-specific filenames.",
      "Scout explains what to check at each review checkpoint and when the evidence search begins.",
    ] }],
  },
  {
    version: "0.4.0",
    title: "Broader Inspector guideline coverage",
    sections: [{ changes: [
      "Inspector adds selected WHO, FDA and EMA review rubrics for vaccines, diagnostics and devices.",
      "A few product questions decide which of these reviews apply. They review the document and are not regulatory compliance checks.",
    ] }],
  },
  {
    version: "0.3.0",
    title: "Clearer evidence review and document coverage",
    sections: [{ changes: [
      "Rerun Scout to use this version: Scout results saved by earlier versions cannot be imported.",
      "Scout extracts numeric targets more accurately and explains its recommendations and uncertainty more clearly.",
      "Scout compares evidence only when it measures the same outcome under comparable conditions, whether or not its value meets the target.",
      "Scout’s review checkpoints are simpler, with editable decisions and clearer source links, and Assistant can explain an active review without changing it.",
      "Better DOCX extraction, full-slide visuals for PPTX, rendered PDF pages in Screener, and fixed section mapping for large documents.",
      "Tool cards show when an analysis is queued, running, ready for review or finished, and a running analysis stays visible when you return to its tool.",
      "Added release notes, Teams feedback contacts and a reminder to verify AI-generated results.",
    ] }],
  },
  {
    version: "0.2.1",
    title: "Scout evidence refinements",
    sections: [{ changes: [
      "Scout tells conflicting evidence apart from differences between products or targets more clearly.",
      "Updated the model Scout uses to extract document targets.",
    ] }],
  },
  {
    version: "0.2.0",
    title: "Broader reviews and document coverage",
    sections: [{ changes: [
      "Inspector can review one document against several rubrics, each with its own result and rubric revision.",
      "Scout extracts IPDP claims and merges duplicates more reliably, with clearer evidence review panels.",
      "Screener reads images embedded in text-based PDFs and explains that format’s limits.",
      "Traces, citations, layouts and progress messages are more consistent across tools.",
      "Added Female Contraception to the indication list.",
    ] }],
  },
  {
    version: "0.1.0",
    title: "Initial production release",
    sections: [{ changes: [
      "Launched the PDIS workspace for document review, evidence checks and stage-gate screening.",
      "Connected the production evidence-retrieval service.",
    ] }],
  },
];

export const CURRENT_RELEASE = RELEASES[0];
