"use client";

import { Plus } from "lucide-react";

import { DownloadButton } from "@/components/download-button";
import { Button } from "@/components/ui/button";
import { WordExportButton, type WordExport } from "@/components/word-export-button";

type Download = {
  filename: string;
  /** Packs the file on click; see `DownloadButton`. */
  data: () => unknown;
};

type Props = {
  onNewAnalysis: () => void;
  download?: Download;
  /** The same final result as a Word file, beside its JSON. */
  word?: WordExport;
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
export function FinalResultActions({ onNewAnalysis, download, word }: Props) {
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
      {word && <WordExportButton {...word} />}
    </>
  );
}
