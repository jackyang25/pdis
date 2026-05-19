"use client";

import { Download } from "lucide-react";
import { Button } from "./ui/button";

type Props = {
  filename: string;
  data: unknown;
  /** "json" pretty-prints; "jsonl" emits one JSON object per line. */
  format?: "json" | "jsonl";
  label?: string;
};

export function DownloadButton({ filename, data, format = "json", label = "Download" }: Props) {
  function handleClick() {
    const content =
      format === "jsonl" && Array.isArray(data)
        ? data.map((item) => JSON.stringify(item)).join("\n")
        : JSON.stringify(data, null, 2);
    const blob = new Blob([content], {
      type: format === "jsonl" ? "application/x-ndjson" : "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <Button variant="outline" size="sm" onClick={handleClick}>
      <Download className="mr-2 h-3.5 w-3.5" />
      {label}
    </Button>
  );
}
