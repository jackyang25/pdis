"use client";

import { useRef, useState } from "react";
import { Check, Loader2, Plus, Upload, X } from "lucide-react";
import { Button } from "./ui/button";
import { Label } from "./ui/label";
import { ErrorMessage } from "./ui/error-message";
import { EmptyState } from "./empty-state";
import { ProgressSteps, type Step } from "./progress-steps";
import {
  STRUCTURED_DOCUMENT_FORMATS,
  type DocumentFormats,
  isSupportedDocument,
} from "@/lib/document-formats";
import { placeFiles } from "@/lib/document-slots";
import { cn } from "@/lib/utils";

/** One upload slot, identified by a role or by its place in a document collection. */
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
  /**
   * Upload slots in display order. Defaults to one unlabeled document.
   *
   * `null` for a tool that reads no document (Drafter): no upload area, and Run waits only
   * on the configuration. Distinct from an empty list, which is a tool that has not chosen
   * its documents yet and so cannot run.
   */
  documents?: readonly DocumentSlot[] | null;
  /** One capability governs the picker, drag/drop validation, and format hint. */
  documentFormats?: DocumentFormats;
  /** Explain an empty slot list before the caller has chosen document roles. */
  emptyDocumentsHint?: string;
  /**
   * Optional collection controls; the caller owns document identity and order. Adding returns
   * the new slot's id, so several files picked or dropped together can each take one.
   */
  onAddDocument?: () => string;
  onRemoveDocument?: (id: string) => void;
  disabled?: boolean;
  busy?: boolean;
  startedAt?: number | null;
  /** Called once every required slot holds a supported file; files are keyed by slot id. */
  onRun: (files: Record<string, File>) => void;
  /** The page owns parsing and saved-result compatibility; this owns the picker. */
  onImport?: (file: File) => void;
  steps?: Step[];
  /** Backend stage key currently active. Drives ProgressSteps. */
  currentStage?: string | null;
  /** Optional live item count for the active stage. */
  progress?: { completed: number; total: number } | null;
  /** Gate only the Run action (e.g. header not selected) while keeping the
   * file picker and saved-result import usable. */
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
  documentFormats = STRUCTURED_DOCUMENT_FORMATS,
  emptyDocumentsHint = "Complete the configuration to add documents.",
  onAddDocument,
  onRemoveDocument,
  disabled,
  busy,
  startedAt,
  onRun,
  onImport,
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
  const importRef = useRef<HTMLInputElement>(null);

  function chooseFile(slotId: string, picked: File | null) {
    const rejected = picked !== null && !isSupportedDocument(picked.name, documentFormats.suffixes);
    setTypeError(
      rejected ? `Unsupported file type. Supports ${documentFormats.hint}.` : null,
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

  // A collection takes several files at once: any of its slots accepts any document, so a
  // pick or drop fills the slot, then the empty ones, then new ones. A tool whose slots are
  // roles keeps one file per pick, because only the reader knows which role a file is.
  function chooseFiles(slotId: string, picked: File[]) {
    if (!onAddDocument) {
      chooseFile(slotId, picked[0] ?? null);
      return;
    }
    const { placed, overflow, unsupported, repeated } = placeFiles({
      slotId,
      picked,
      slotIds: (documents ?? []).map((slot) => slot.id),
      held: files,
      suffixes: documentFormats.suffixes,
    });
    const added = Object.fromEntries(overflow.map((file) => [onAddDocument(), file]));
    setTypeError([
      unsupported.length ? `Unsupported file type: ${unsupported.join(", ")}. Supports ${documentFormats.hint}.` : "",
      repeated.length ? `Already added: ${repeated.join(", ")}. Each document needs a distinct filename.` : "",
    ].filter(Boolean).join(" ") || null);
    setFiles((current) => {
      const next = { ...current, ...placed, ...added };
      // As with one file: a pick that placed nothing in this slot leaves it empty.
      if (!placed[slotId]) delete next[slotId];
      return next;
    });
  }

  // `every` is true for an empty list, so a tool that has not decided on its
  // documents yet would otherwise enable Run with nothing attached.
  const complete = documents === null || (documents.length > 0 && documents.every((slot) => files[slot.id]));

  return (
    <section
      className={cn(
        "rounded-lg bg-card p-5 shadow-raised sm:p-6",
        className,
      )}
    >
      <div
        className={cn(
          configuration && "grid items-start gap-8 lg:grid-cols-[17rem_minmax(0,1fr)]",
        )}
      >
        {configuration && (
          <div>
            {configuration}
          </div>
        )}
        <div className="flex min-w-0 flex-col gap-4">
          <div className={cn("flex min-h-6 flex-wrap items-center gap-2", documents ? "justify-between" : "justify-end")}>
            {documents && <h2 className="text-sm font-semibold">Documents</h2>}
            {onImport && (
              <>
                <button
                  type="button"
                  onClick={() => importRef.current?.click()}
                  disabled={disabled || busy}
                  className="min-h-6 rounded-sm px-2 text-xs font-medium text-muted-foreground underline decoration-border underline-offset-4 hover:text-foreground focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:opacity-50"
                >
                  Import result
                </button>
                <input
                  ref={importRef}
                  type="file"
                  accept=".json,application/json"
                  className="hidden"
                  onChange={(event) => {
                    const file = event.target.files?.[0];
                    event.target.value = "";
                    if (file) onImport(file);
                  }}
                />
              </>
            )}
          </div>
          {documents && (
            <>
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
            {documents.length === 0 && (
              <EmptyState message="Add documents" detail={emptyDocumentsHint} />
            )}
            {documents.map((slot) => (
              <DocumentField
                key={slot.id}
                slot={slot}
                formats={documentFormats}
                file={files[slot.id] ?? null}
                multiple={Boolean(onAddDocument)}
                disabled={disabled || busy}
                onRemove={
                  onRemoveDocument && documents.length > 1
                    ? () => {
                        chooseFile(slot.id, null);
                        onRemoveDocument(slot.id);
                      }
                    : undefined
                }
                onChange={(picked) => chooseFiles(slot.id, picked)}
              />
            ))}
          </div>
          {onAddDocument && (
            <Button
              variant="ghost"
              size="sm"
              type="button"
              onClick={onAddDocument}
              disabled={disabled || busy}
              className="self-start justify-self-start gap-1.5 text-muted-foreground"
            >
              <Plus aria-hidden="true" className="h-3.5 w-3.5" />
              Add document
            </Button>
          )}
          {typeError && <ErrorMessage size="xs">{typeError}</ErrorMessage>}
          {documentFormats.note && (
            <p className="text-xs leading-relaxed text-muted-foreground">{documentFormats.note}</p>
          )}

            </>
          )}

          {/* While running, the checklist is several lines tall, so the button sits at its
              foot rather than floating beside its middle. */}
          <div className={cn("mt-2 flex flex-col items-stretch justify-between gap-3 sm:flex-row", steps && busy ? "sm:items-end" : "sm:items-center")}>
            <div className="flex min-h-9 min-w-0 items-center">
              {steps && busy ? (
                <ProgressSteps
                  steps={steps}
                  busy={busy}
                  startedAt={startedAt ?? null}
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
                  {/* The checklist beside it already turns on the active stage; a second
                      spinner here would say the same thing twice. */}
                  {!steps && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                  {busyLabel}…
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
  formats,
  file,
  multiple = false,
  disabled,
  onChange,
  onRemove,
}: {
  slot: DocumentSlot;
  formats: DocumentFormats;
  file: File | null;
  /** Whether a pick or drop may carry several files; the panel decides where they go. */
  multiple?: boolean;
  disabled?: boolean;
  onChange: (files: File[]) => void;
  onRemove?: () => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);

  return (
    <div className="flex min-w-0 flex-col gap-2">
      <div className="flex items-baseline justify-between gap-4">
        <Label>{slot.label}</Label>
        <span className="text-[10px] text-muted-foreground">
          {formats.hint}
        </span>
        {onRemove && (
          <Button
            variant="ghost"
            size="icon"
            type="button"
            onClick={onRemove}
            disabled={disabled}
            aria-label={`Remove ${slot.label.toLowerCase()}`}
            className="shrink-0 text-muted-foreground"
          >
            <X aria-hidden="true" className="h-3.5 w-3.5" />
          </Button>
        )}
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
          if (!disabled) onChange(Array.from(event.dataTransfer.files ?? []));
        }}
        disabled={disabled}
        className={cn(
          // Grows for a wrapped prompt in a narrow slot; one line stays 60px.
          "flex min-h-[60px] w-full items-center gap-3 rounded-md border border-dashed border-input bg-foreground/[0.045] px-4 py-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/20 motion-reduce:transition-none",
          !disabled && "hover:border-foreground/25 hover:bg-foreground/[0.045]",
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
              {multiple ? "Drop files here or choose from your computer" : "Drop a file here or choose from your computer"}
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
        accept={formats.accept}
        multiple={multiple}
        className="hidden"
        onChange={(event) => onChange(Array.from(event.target.files ?? []))}
      />
    </div>
  );
}
