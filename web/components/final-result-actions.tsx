"use client";

import { Plus } from "lucide-react";

import { DownloadButton } from "@/components/download-button";
import { Button } from "@/components/ui/button";
import { ResultExportMenu, type ResultExport } from "@/components/result-export-menu";

type Download = {
  filename: string;
  /** Packs the file on click; see `DownloadButton`. */
  data: () => unknown;
};

type Props = {
  onNewAnalysis: () => void;
  download?: Download;
  /** The same final result as a Word or Excel file, beside its JSON. */
  fileExport?: ResultExport;
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
    <Button variant="quiet" size="toolbar" onClick={onClick} disabled={disabled}>
      <Plus aria-hidden="true" />
      New analysis
    </Button>
  );
}

/** Shared actions for immutable, portable tool results. */
export function FinalResultActions({ onNewAnalysis, download, fileExport }: Props) {
  return (
    <>
      <NewAnalysisButton onClick={onNewAnalysis} />
      {download && (
        <DownloadButton
          filename={download.filename}
          data={download.data}
          label="Download JSON"
        />
      )}
      {fileExport && <ResultExportMenu {...fileExport} />}
    </>
  );
}
