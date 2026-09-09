import { AlertTriangle } from "lucide-react";
import type { ContentBlock } from "@/lib/api";
import { documentExtractionWarnings } from "@/lib/document-extraction";

export function DocumentExtractionNotice({ blocks }: { blocks: ContentBlock[] }) {
  const warnings = documentExtractionWarnings(blocks);
  if (!warnings.length) return null;
  return (
    <aside aria-label="Document extraction limitations" className="flex items-start gap-2.5 rounded-lg border border-[hsl(var(--tone-warning))]/30 bg-[hsl(var(--tone-warning))]/[0.07] px-3.5 py-3 text-xs text-foreground">
      <AlertTriangle aria-hidden="true" className="mt-0.5 h-3.5 w-3.5 shrink-0" />
      <div className="min-w-0 space-y-2">
        {warnings.map(({ code, documentIds }) => (
          <div key={code}>
            <p className="font-medium">{documentIds.join(", ")}</p>
            <p className="mt-0.5 leading-relaxed text-muted-foreground">
              {code === "pdf_text_only"
                ? "PDF text only. Images and scanned content are not read; columns and tables may be misordered. Citations point to extracted page text, not a verified reconstruction. Check the original before relying on the result."
                : "The parser reported an extraction limitation. Check the original before relying on the result."}
            </p>
          </div>
        ))}
      </div>
    </aside>
  );
}
