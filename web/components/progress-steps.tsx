"use client";

import { Loader2 } from "lucide-react";

export type Step = { key: string; label: string };

type Props = {
  steps: Step[];
  busy: boolean;
  /** The key of the currently active step (set from a server-sent stage event). */
  currentStage: string | null;
  /** Optional live item count for the active stage (e.g. searches completed). */
  progress?: { completed: number; total: number } | null;
};

export function ProgressSteps({ steps, busy, currentStage, progress }: Props) {
  if (!busy) return null;

  const foundIndex = currentStage
    ? steps.findIndex((step) => step.key === currentStage)
    : -1;
  const activeIndex = foundIndex >= 0 ? foundIndex : 0;
  const activeStep = steps[activeIndex];
  const hasCount = !!progress && progress.total > 0;

  return (
    <div
      role="status"
      aria-live="polite"
      aria-atomic="true"
      className="flex min-w-0 items-center gap-2 text-xs"
    >
      <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-muted-foreground" />
      <span className="min-w-0 truncate font-medium text-foreground">
        {activeStep?.label ?? "Starting analysis"}
      </span>
      <span className="shrink-0 tabular-nums text-muted-foreground">
        {activeIndex + 1} of {steps.length}
      </span>
      {hasCount && (
        <span className="shrink-0 tabular-nums text-muted-foreground">
          · {progress.completed}/{progress.total}
        </span>
      )}
    </div>
  );
}
