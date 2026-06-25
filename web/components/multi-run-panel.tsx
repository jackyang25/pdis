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
  onRun: (files: File[]) => void;
  extraControls?: React.ReactNode;
  steps?: Step[];
  /** Backend stage key currently active. Drives ProgressSteps. */
  currentStage?: string | null;
  /** Optional live item count for the active stage. */
  progress?: { completed: number; total: number } | null;
  /** Optional label override (default: "Documents") */
  label?: string;
};

export function MultiRunPanel({
  accept,
  disabled,
  busy,
  onRun,
  extraControls,
  steps,
  currentStage,
  progress,
  label = "Documents",
}: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<File[]>([]);

  return (
    <div className="flex flex-col gap-4 rounded-lg border border-border bg-card p-6">
      <div>
        <Label className="mb-2 block">{label}</Label>
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
            {files.length === 0
              ? "Click to choose one or more files"
              : files.length === 1
                ? files[0].name
                : `${files.length} files selected`}
          </span>
        </button>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept={accept}
          className="hidden"
          onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
        />
        {files.length > 1 && (
          <ul className="mt-2 text-xs text-muted-foreground">
            {files.map((file) => (
              <li key={`${file.name}-${file.lastModified}`} className="truncate">
                - {file.name}
              </li>
            ))}
          </ul>
        )}
      </div>

      {extraControls}

      <Button
        onClick={() => files.length > 0 && onRun(files)}
        disabled={disabled || busy || files.length === 0}
      >
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
