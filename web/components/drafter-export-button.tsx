"use client";

import { useState } from "react";
import { FileText, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { exportDrafterDocx, type DraftResult } from "@/lib/api";

/** A final draft as a Word table, built by the server from the same final result. */
export function DrafterExportButton({ result, onError }: { result: DraftResult; onError: (message: string) => void }) {
  const [busy, setBusy] = useState(false);
  return (
    <Button
      size="sm"
      variant="outline"
      disabled={busy}
      onClick={async () => {
        setBusy(true);
        try {
          const { blob, filename } = await exportDrafterDocx(result);
          const url = URL.createObjectURL(blob);
          const link = document.createElement("a");
          link.href = url;
          link.download = filename;
          link.click();
          URL.revokeObjectURL(url);
        } catch (error) {
          onError(`Could not export the draft: ${(error as Error).message}`);
        } finally {
          setBusy(false);
        }
      }}
    >
      {/* The same mark and spacing as the JSON download beside it. */}
      {busy
        ? <Loader2 aria-hidden="true" className="mr-2 h-3.5 w-3.5 animate-spin" strokeWidth={1.8} />
        : <FileText aria-hidden="true" className="mr-2 h-3.5 w-3.5" strokeWidth={1.8} />}
      Export Word table
    </Button>
  );
}
