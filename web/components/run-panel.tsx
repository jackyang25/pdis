"use client";

import { useRef, useState } from "react";
import { Check, Loader2, Upload } from "lucide-react";
import { Button } from "./ui/button";
import { Label } from "./ui/label";
import { ErrorMessage } from "./ui/error-message";
import { ProgressSteps, type Step } from "./progress-steps";
import {
  DOCUMENT_ACCEPT,
  DOCUMENT_FORMAT_HINT,
  isSupportedDocument,
} from "@/lib/document-formats";
import { cn } from "@/lib/utils";

/** One upload slot. Tools that read more than one document name each role. */
export type DocumentSlot = {
  /** Keys the chosen file back to the caller in `onRun`. */
  id: string;
  label: string;
  /** Why this document rather than the other one. Shown only when slots differ. */
  helper?: string;
};

const SINGLE_DOCUMENT: readonly DocumentSlot[] = [
  { id: "document", label: "Document" },
];

type Props = {
  className?: string;
  configuration?: React.ReactNode;
  /** Upload slots in display order. Defaults to one unlabeled document. */
  documents?: readonly DocumentSlot[];
  disabled?: boolean;
  busy?: boolean;
  /** Called once every slot holds a supported file, keyed by slot id. */
  onRun: (files: Record<string, File>) => void;
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
  /** Verb for this tool's run, e.g. `Run alignment`. Defaults to `Run analysis`. */
  runLabel?: string;
  /** Present tense shown while running, e.g. `Aligning`. Defaults to `Running`. */
  busyLabel?: string;
};

export function RunPanel({
  className,
  configuration,
  documents = SINGLE_DOCUMENT,
  disabled,
  busy,
  onRun,
  extraControls,
  steps,
  currentStage,
  progress,
  runDisabled,
  hint,
  runLabel = "Run analysis",
  busyLabel = "Running",
}: Props) {
  const [files, setFiles] = useState<Record<string, File>>({});
  const [typeError, setTypeError] = useState<string | null>(null);

  function chooseFile(slotId: string, picked: File | null) {
    const rejected = picked !== null && !isSupportedDocument(picked.name);
    setTypeError(
      rejected ? `Unsupported file type. Supports ${DOCUMENT_FORMAT_HINT}.` : null,
    );
    setFiles((current) => {
      const next = { ...current };
      // Clearing and rejecting both leave the slot empty, so a stale file can
      // never survive a failed pick and reach `onRun`.
      if (picked && !rejected) next[slotId] = picked;
      else delete next[slotId];
      return next;
    });
  }

  // `every` is true for an empty list, so a tool that has not decided on its
  // documents yet would otherwise enable Run with nothing attached.
  const complete = documents.length > 0 && documents.every((slot) => files[slot.id]);

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
          <div
            className={cn(
              // Two columns at most, whatever the slot count. Three across put each
              // drop zone under about 170px beside the configuration rail, which is
              // too narrow to read a filename in — the reason the third column
              // existed was to avoid a two-over-one row, and an unreadable row is
              // worse than an uneven one. A fourth document wraps to a third row.
              documents.length > 1 && "grid gap-4 sm:grid-cols-2",
            )}
          >
            {documents.map((slot) => (
              <DocumentField
                key={slot.id}
                slot={slot}
                file={files[slot.id] ?? null}
                disabled={disabled}
                onChange={(picked) => chooseFile(slot.id, picked)}
              />
            ))}
          </div>
          {typeError && <ErrorMessage size="xs">{typeError}</ErrorMessage>}

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
              onClick={() => complete && onRun(files)}
              disabled={disabled || busy || !complete || runDisabled}
            >
              {busy ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  {busyLabel}
                </>
              ) : (
                runLabel
              )}
            </Button>
          </div>

        </div>
      </div>
    </section>
  );
}

/** One labeled drop zone. Every tool's upload affordance is this component. */
function DocumentField({
  slot,
  file,
  disabled,
  onChange,
}: {
  slot: DocumentSlot;
  file: File | null;
  disabled?: boolean;
  onChange: (file: File | null) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);

  return (
    <div className="flex min-w-0 flex-col gap-2">
      <div className="flex items-baseline justify-between gap-4">
        <Label>{slot.label}</Label>
        <span className="text-[10px] text-muted-foreground">
          {DOCUMENT_FORMAT_HINT}
        </span>
      </div>
      {slot.helper && (
        <p className="text-[11px] leading-4 text-muted-foreground">{slot.helper}</p>
      )}
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        onDragOver={(event) => event.preventDefault()}
        onDrop={(event) => {
          event.preventDefault();
          if (!disabled) onChange(event.dataTransfer.files?.[0] ?? null);
        }}
        disabled={disabled}
        className={cn(
          // Grows for a wrapped prompt in a narrow slot; one line stays 60px.
          "flex min-h-[60px] w-full items-center gap-3 rounded-md border border-dashed border-input bg-muted/20 px-4 py-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/20 motion-reduce:transition-none",
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
          {file ? (
            // A filename has no useful truncation point, so clip it and keep the
            // row one line tall.
            <span className="block truncate text-sm">{file.name}</span>
          ) : (
            // The prompt wraps instead: in a two-slot layout each field is half
            // width, and a clipped instruction reads as broken rather than terse.
            <span className="block text-sm leading-5">
              Drop a file here or choose from your computer
            </span>
          )}
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
        accept={DOCUMENT_ACCEPT}
        className="hidden"
        onChange={(event) => onChange(event.target.files?.[0] ?? null)}
      />
    </div>
  );
}
