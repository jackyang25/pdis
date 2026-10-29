"use client";

import { useState } from "react";
import { ChevronDown, FileSpreadsheet, FileText, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { exportResultFile, type ExportFormat, type ExportTool } from "@/lib/api";
import { saveBlob } from "@/lib/save-file";

export type ResultExport = {
  tool: ExportTool;
  /** The final result, in the shape its run returned it. */
  result: Parameters<typeof exportResultFile>[1];
  onError: (message: string) => void;
};

/** The files a result exports to, named for the program that opens them. */
const FORMATS: { format: ExportFormat; label: string; app: string; Icon: typeof FileText }[] = [
  { format: "docx", label: "Word document", app: "Word", Icon: FileText },
  { format: "xlsx", label: "Excel workbook", app: "Excel", Icon: FileSpreadsheet },
];

/**
 * A final result as a Word or Excel file, built by the server from the same result: one menu
 * for every tool. One control rather than a button per format, so a result's header keeps
 * one export action beside its JSON download however many formats there are.
 */
export function ResultExportMenu({ tool, result, onError }: ResultExport) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  async function exportAs(format: ExportFormat, app: string) {
    setOpen(false);
    setBusy(true);
    try {
      const { blob, filename } = await exportResultFile(tool, result, format);
      saveBlob(blob, filename);
    } catch (error) {
      onError(`Could not export to ${app}: ${(error as Error).message}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button size="toolbar" variant="outline" disabled={busy}>
          {/* The same mark and spacing as the JSON download beside it. */}
          {busy ? <Loader2 aria-hidden="true" className="animate-spin" /> : <FileText aria-hidden="true" />}
          Export
          <ChevronDown aria-hidden="true" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-52 p-1">
        <ul className="space-y-0.5">
          {FORMATS.map(({ format, label, app, Icon }) => (
            <li key={format}>
              <button
                type="button"
                onClick={() => exportAs(format, app)}
                className="flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-left text-xs text-foreground transition-colors hover:bg-foreground/[0.045] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/60 motion-reduce:transition-none"
              >
                <Icon aria-hidden="true" className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                <span className="flex-1 font-medium">{label}</span>
                <span className="text-muted-foreground">.{format}</span>
              </button>
            </li>
          ))}
        </ul>
      </PopoverContent>
    </Popover>
  );
}
