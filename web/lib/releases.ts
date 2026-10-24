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
    version: "0.8.0",
    title: "More reliable results, clearer pages",
    sections: [
      {
        title: "Results",
        changes: [
          "A check that could not run now says “Not assessed” instead of looking like an answer, and a field with no evidence says so.",
          "Scout’s judgements read each source’s title, date and opening words, and Drafter checks every number against the words that state it.",
          "Searches find much more: PubMed and Europe PMC queries return many more relevant records, and repeated records from different sources are merged.",
          "Word form fields and PowerPoint decks with hidden slides are read in full.",
        ],
      },
      {
        title: "Scout",
        changes: [
          "At the review checkpoint, choose which fields to search. Fewer fields make a faster run.",
          "Review explanations are written in plain words.",
        ],
      },
      {
        title: "Everywhere",
        changes: [
          "Report a problem with any finding: an email opens with the finding’s details filled in.",
          "Clicking a highlighted passage in a PDF opens its details, and each tool’s Documents view opens on a layer with marks.",
          "Clearer error messages, a visible keyboard focus, and one consistent look for buttons, counts and lists.",
          "Closing a tab now stops its run, and a dropped connection no longer leaves a run waiting.",
        ],
      },
    ],
  },
  {
    version: "0.7.0",
    title: "Drafter, and smoother Screener and Scout runs",
    sections: [
      {
        title: "Drafter",
        changes: [
          "New tool: Drafter suggests iTPP targets for a product type and disease, each with what comparable products achieved and what published guidance asks, cited to the source.",
          "Download the draft, or export it as a Word table that lists each suggested target with its sources.",
        ],
      },
      {
        title: "Screener",
        changes: [
          "Drop or choose several documents at once.",
          "The coverage grid shows required questions as solid squares and anticipatory ones as outlines.",
        ],
      },
      {
        title: "Scout",
        changes: [
          "IPDP runs extract fewer, more checkable claims: progress updates on the programme’s own work are no longer searched.",
          "Documents whose filenames contain square brackets no longer fail at claim extraction.",
          "Comparator details and the evidence map read more cleanly.",
        ],
      },
    ],
  },
  {
    version: "0.6.0",
    title: "Priorities in every tool and suggested searches in Assistant",
    sections: [{ changes: [
      "Inspector, Aligner, Scout and Screener open with a Priorities card: an AI summary of the result and a few points to look at first, each linked to the findings and passages it rests on.",
      "Priorities name each finding exactly as the result below it does, and you can try again if the summary doesn’t load.",
      "When your results don’t cover a question, Assistant can set up a Searcher run for you to review and start.",
      "Assistant’s citations show which kind of file each passage comes from, and where in it.",
      "Notes about how a file was read now appear as a short caveat rather than a warning.",
    ] }],
  },
  {
    version: "0.5.1",
    title: "PDIS tools only",
    sections: [{ changes: [
      "The Tools page now lists only PDIS’s own tools; the GHIDE workflow links to ChatGPT and Claude were removed.",
    ] }],
  },
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
