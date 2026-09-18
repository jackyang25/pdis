import { WarningNotice } from "@/components/ui/warning-notice";
import type { ContentBlock } from "@/lib/api";
import { documentExtractionWarnings } from "@/lib/document-extraction";
import warningDescriptions from "../../shared/document-extraction.json";

export function DocumentExtractionNotice({ blocks, hasDocumentsTab = true }: {
  blocks: ContentBlock[];
  /** Scout checkpoints offer source passages, not the results' Documents view. */
  hasDocumentsTab?: boolean;
}) {
  const warnings = documentExtractionWarnings(blocks);
  if (!warnings.length) return null;
  return (
    <WarningNotice label="Document extraction limitations" summary="Document extraction limitations">
      {warnings.map(({ code, documentIds, details }) => (
        <div key={code}>
          <p className="font-medium">{documentIds.join(", ")}</p>
          <p className="mt-0.5 leading-relaxed text-muted-foreground">
            {(warningDescriptions as Record<string, string>)[code]
              ?? "The parser reported an extraction limitation. Check the original before relying on the result."}
          </p>
          {details?.map((detail) => (
            <p key={detail} className="mt-0.5 leading-relaxed text-muted-foreground">{detail}</p>
          ))}
        </div>
      ))}
      <p className="leading-relaxed text-muted-foreground">
        {hasDocumentsTab
          ? "Review captured text and visuals in the Documents tab."
          : "Use any available source links in this review to inspect cited content."}
      </p>
    </WarningNotice>
  );
}
