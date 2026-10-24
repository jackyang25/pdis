"use client";

import { useState } from "react";
import { FileText, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { exportDrafterDocx, type DraftResult } from "@/lib/api";
import { saveBlob } from "@/lib/save-file";

/** A final draft as a Word table, built by the server from the same final result. */
export function DrafterExportButton({ result, onError }: { result: DraftResult; onError: (message: string) => void }) {
  const [busy, setBusy] = useState(false);
  return (
    <Button
      size="toolbar"
      variant="outline"
      disabled={busy}
      onClick={async () => {
        setBusy(true);
        try {
          const { blob, filename } = await exportDrafterDocx(result);
          saveBlob(blob, filename);
        } catch (error) {
          onError(`Could not export the draft: ${(error as Error).message}`);
        } finally {
          setBusy(false);
        }
      }}
    >
      {/* The same mark and spacing as the JSON download beside it. */}
      {busy ? <Loader2 aria-hidden="true" className="animate-spin" /> : <FileText aria-hidden="true" />}
      Export Word table
    </Button>
  );
}
