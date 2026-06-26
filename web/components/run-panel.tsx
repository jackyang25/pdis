"use client";

import { useRef, useState } from "react";
import { Loader2, Upload } from "lucide-react";
import { Button } from "./ui/button";
import { Label } from "./ui/label";
import { ProgressSteps, type Step } from "./progress-steps";
import { cn } from "@/lib/utils";

type Props = {
  accept: string;
  disabled?: boolean;
  busy?: boolean;
  onRun: (file: File) => void;
  extraControls?: React.ReactNode;
  steps?: Step[];
  /** Backend stage key currently active. Drives ProgressSteps. */
  currentStage?: string | null;
  /** Optional live item count for the active stage. */
  progress?: { completed: number; total: number } | null;
};

export function RunPanel({
  accept,
  disabled,
  busy,
  onRun,
  extraControls,
  steps,
  currentStage,
  progress,
}: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [typeError, setTypeError] = useState<string | null>(null);

  // Single source of truth for supported types: derive both the displayed hint
  // and the validation from `accept`, so they can never drift apart.
  const exts = accept.split(",").map((s) => s.trim().toLowerCase()).filter(Boolean);
  const acceptHint = exts.map((e) => e.replace(/^\./, "").toUpperCase()).join(", ");

  function chooseFile(picked: File | null) {
    if (picked && !exts.some((e) => picked.name.toLowerCase().endsWith(e))) {
      setTypeError(`Unsupported file type. Supports ${acceptHint}.`);
      setFile(null);
      return;
    }
    setTypeError(null);
    setFile(picked);
  }

  return (
    <div className="flex flex-col gap-4 rounded-lg border border-border bg-card p-6">
      <div>
        <Label className="mb-2 block">Document</Label>
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          disabled={disabled}
          className={cn(
            "flex w-full items-center gap-3 rounded-md border border-dashed border-border bg-background px-4 py-3 text-left text-sm transition-colors",
            !disabled && "hover:bg-accent",
            disabled && "cursor-not-allowed opacity-60",
          )}
        >
          <Upload className="h-4 w-4 text-muted-foreground" />
          <span className="flex-1 truncate text-muted-foreground">
            {file ? file.name : "Click to choose file"}
          </span>
        </button>
        <input
          ref={inputRef}
          type="file"
          accept={accept}
          className="hidden"
          onChange={(e) => chooseFile(e.target.files?.[0] ?? null)}
        />
        <p className="mt-1.5 text-[11px] text-muted-foreground">Supports {acceptHint}</p>
        {typeError && <p className="mt-1 text-[11px] text-destructive">{typeError}</p>}
      </div>

      {extraControls}

      <Button onClick={() => file && onRun(file)} disabled={disabled || busy || !file}>
        {busy ? (
          <>
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            Processing
          </>
        ) : (
          "Run"
        )}
      </Button>

      {steps && (
        <ProgressSteps
          steps={steps}
          busy={!!busy}
          currentStage={currentStage ?? null}
          progress={progress ?? null}
        />
      )}
    </div>
  );
}
