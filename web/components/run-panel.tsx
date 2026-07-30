"use client";

import { useRef, useState } from "react";
import { Check, Loader2, Upload } from "lucide-react";
import { Button } from "./ui/button";
import { Label } from "./ui/label";
import { ProgressSteps, type Step } from "./progress-steps";
import { cn } from "@/lib/utils";

type Props = {
  className?: string;
  configuration?: React.ReactNode;
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
  /** Gate only the Run action (e.g. header not selected) while keeping the
   * file picker and any extraControls (Import) usable. */
  runDisabled?: boolean;
  /** Muted hint shown near the Run button (e.g. why Run is gated). */
  hint?: string;
};

export function RunPanel({
  className,
  configuration,
  accept,
  disabled,
  busy,
  onRun,
  extraControls,
  steps,
  currentStage,
  progress,
  runDisabled,
  hint,
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
    <section
      className={cn(
        "rounded-lg border border-border bg-card p-5 sm:p-6",
        className,
      )}
    >
      <div
        className={cn(
          "h-full",
          configuration && "grid gap-6 lg:grid-cols-[17rem_minmax(0,1fr)]",
        )}
      >
        {configuration && (
          <div className="border-b border-border/80 pb-6 lg:border-b-0 lg:border-r lg:pb-0 lg:pr-6">
            {configuration}
          </div>
        )}
        <div className="flex h-full flex-col gap-4">
          <div className="flex items-center justify-between gap-4">
            <Label>Document</Label>
            <span className="text-[10px] text-muted-foreground">{acceptHint}</span>
          </div>
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            onDragOver={(event) => event.preventDefault()}
            onDrop={(event) => {
              event.preventDefault();
              if (!disabled) chooseFile(event.dataTransfer.files?.[0] ?? null);
            }}
            disabled={disabled}
            className={cn(
              "flex h-[60px] w-full items-center gap-3 rounded-md border border-dashed border-input bg-muted/20 px-4 py-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/20 motion-reduce:transition-none",
              !disabled && "hover:border-foreground/25 hover:bg-muted/45",
              disabled && "cursor-not-allowed opacity-60",
            )}
          >
            <span className="text-muted-foreground">
              {file ? (
                <Check className="h-4 w-4 text-foreground" />
              ) : (
                <Upload className="h-4 w-4" />
              )}
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm">
                {file ? file.name : "Drop a file here or choose from your computer"}
              </span>
              {file && (
                <span className="mt-0.5 block text-[11px] text-muted-foreground">
                  {(file.size / 1024 / 1024).toFixed(2)} MB
                </span>
              )}
            </span>
            <span className="text-xs font-medium text-muted-foreground">Browse</span>
          </button>
          <input
            ref={inputRef}
            type="file"
            accept={accept}
            className="hidden"
            onChange={(e) => chooseFile(e.target.files?.[0] ?? null)}
          />
          {typeError && <p className="mt-1 text-[11px] text-destructive">{typeError}</p>}

          {extraControls}

          <div className="mt-auto flex flex-col-reverse items-stretch justify-between gap-3 sm:flex-row sm:items-center">
            <div className="flex min-h-9 min-w-0 items-center">
              {steps && busy ? (
                <ProgressSteps
                  steps={steps}
                  busy={busy}
                  currentStage={currentStage ?? null}
                  progress={progress ?? null}
                />
              ) : hint ? (
                <p className="text-xs text-muted-foreground">{hint}</p>
              ) : null}
            </div>
            <Button
              className="min-w-[7.5rem]"
              onClick={() => file && onRun(file)}
              disabled={disabled || busy || !file || runDisabled}
            >
              {busy ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Running
                </>
              ) : (
                "Run analysis"
              )}
            </Button>
          </div>

        </div>
      </div>
    </section>
  );
}
