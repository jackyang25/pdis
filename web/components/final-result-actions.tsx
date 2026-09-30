"use client";

import { Plus } from "lucide-react";

import { DownloadButton } from "@/components/download-button";
import { Button } from "@/components/ui/button";

type Download = {
  filename: string;
  data: unknown;
};

type Props = {
  onNewAnalysis: () => void;
  download?: Download;
};

/**
 * Start again from setup. One button wherever a run can be left: a finished result's header
 * and each Scout review checkpoint drew their own, and only one of them carried the icon.
 *
 * Iconed like Metrics beside it, so a header's quiet actions share one shape and Download
 * stays the one bordered button.
 */
export function NewAnalysisButton({ onClick, disabled }: { onClick: () => void; disabled?: boolean }) {
  return (
    <Button variant="ghost" size="sm" onClick={onClick} disabled={disabled} className="gap-1.5 px-2 text-muted-foreground hover:text-foreground">
      <Plus aria-hidden="true" className="h-3.5 w-3.5" />
      New analysis
    </Button>
  );
}

/** Shared actions for immutable, portable tool results. */
export function FinalResultActions({ onNewAnalysis, download }: Props) {
  return (
    <>
      <NewAnalysisButton onClick={onNewAnalysis} />
      {download && (
        <DownloadButton
          filename={download.filename}
          data={download.data}
          format="json"
          label="Download JSON"
        />
      )}
    </>
  );
}
