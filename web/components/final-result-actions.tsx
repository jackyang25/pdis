"use client";

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

/** Shared actions for immutable, portable tool results. */
export function FinalResultActions({ onNewAnalysis, download }: Props) {
  return (
    <>
      <Button variant="ghost" size="sm" onClick={onNewAnalysis}>
        New analysis
      </Button>
      {download && (
        <DownloadButton
          filename={download.filename}
          data={download.data}
          format="json"
          label="Download final JSON"
        />
      )}
    </>
  );
}
