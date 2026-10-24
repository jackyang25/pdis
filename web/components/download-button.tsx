"use client";

import { Download } from "lucide-react";
import { saveBlob } from "@/lib/save-file";
import { Button } from "./ui/button";

type Props = {
  filename: string;
  /**
   * Builds the file's contents, called on click rather than on every render: packing a
   * result runs its whole contract, which is work a result view must not repeat each
   * time a progress tick re-renders it.
   */
  data: () => unknown;
  label?: string;
};

export function DownloadButton({ filename, data, label = "Download" }: Props) {
  function handleClick() {
    const blob = new Blob([JSON.stringify(data(), null, 2)], { type: "application/json" });
    saveBlob(blob, filename);
  }

  return (
    <Button variant="outline" size="toolbar" onClick={handleClick}>
      <Download aria-hidden="true" />
      {label}
    </Button>
  );
}
