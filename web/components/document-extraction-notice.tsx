import { CaveatNotice } from "@/components/ui/warning-notice";
import type { ContentBlock } from "@/lib/api";
import { documentExtractionWarnings } from "@/lib/document-extraction";
import extractionWarnings from "../../shared/document-extraction.json";

/** Each parser warning in two lengths: a line beside one passage, a paragraph for a result. */
const WARNINGS: Record<string, { summary: string; description: string }> = extractionWarnings;
const UNKNOWN = {
  summary: "The parser reported an extraction limitation here.",
  description: "The parser reported an extraction limitation. Check the original before relying on the result.",
};

/**
 * A result's extraction limitations, as a caveat: the parser read less than the file shows,
 * so quoted words need checking against the page, but the result still says what it says.
 */
export function DocumentExtractionNotice({ blocks, hasDocumentsTab = true }: {
  blocks: ContentBlock[];
  /** Scout checkpoints offer source passages, not the results' Documents view. */
  hasDocumentsTab?: boolean;
}) {
  const warnings = documentExtractionWarnings(blocks);
  if (!warnings.length) return null;
  return (
    <CaveatNotice label="Document extraction limitations" summary="Document extraction limitations">
      {warnings.map(({ code, documentIds, details }) => (
        <div key={code}>
          <p className="font-medium text-foreground">{documentIds.join(", ")}</p>
          <p className="mt-0.5">{(WARNINGS[code] ?? UNKNOWN).description}</p>
          {details?.map((detail) => (
            <p key={detail} className="mt-0.5">{detail}</p>
          ))}
        </div>
      ))}
      <p>
        {hasDocumentsTab
          ? "Review captured text and visuals in the Documents tab."
          : "Use any available source links in this review to inspect cited content."}
      </p>
    </CaveatNotice>
  );
}

/**
 * One passage's limitations, a line each, for where a passage is read on its own - an
 * Assistant citation, which may sit over a page that does not hold its document.
 *
 * The result-wide notice names documents and says where to look; here the document is
 * already named beside the passage and there may be no Documents tab, so only what the
 * limitation means for these words remains. The same parser codes, in their short form, at
 * the same caveat weight as the result's notice.
 */
export function PassageExtractionNote({ block }: { block: ContentBlock }) {
  const warnings = documentExtractionWarnings([block]);
  if (!warnings.length) return null;
  return (
    <div className="mt-2 space-y-1">
      {warnings.map(({ code }) => (
        <CaveatNotice key={code} label="Extraction limitation">
          {(WARNINGS[code] ?? UNKNOWN).summary}
        </CaveatNotice>
      ))}
    </div>
  );
}
