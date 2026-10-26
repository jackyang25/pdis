"use client";

import { useState } from "react";
import { FileText, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { exportWordDocument, type WordExportTool } from "@/lib/api";
import { saveBlob } from "@/lib/save-file";

export type WordExport = {
  tool: WordExportTool;
  /** The final result, in the shape its run returned it. */
  result: Parameters<typeof exportWordDocument>[1];
  onError: (message: string) => void;
};

/** A final result as a Word file, built by the server from the same result: one button for every tool. */
export function WordExportButton({ tool, result, onError }: WordExport) {
  const [busy, setBusy] = useState(false);
  return (
    <Button
      size="toolbar"
      variant="outline"
      disabled={busy}
      onClick={async () => {
        setBusy(true);
        try {
          const { blob, filename } = await exportWordDocument(tool, result);
          saveBlob(blob, filename);
        } catch (error) {
          onError(`Could not export to Word: ${(error as Error).message}`);
        } finally {
          setBusy(false);
        }
      }}
    >
      {/* The same mark and spacing as the JSON download beside it. */}
      {busy ? <Loader2 aria-hidden="true" className="animate-spin" /> : <FileText aria-hidden="true" />}
      Export to Word
    </Button>
  );
}
