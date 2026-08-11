"use client";

import { Loader2 } from "lucide-react";
import { useEffect, useState } from "react";

import { QUEUED_STAGE } from "@/lib/api";
import { formatElapsed } from "@/lib/elapsed";
import { cn } from "@/lib/utils";

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
  const elapsed = useElapsedWhile(busy);

  if (!busy) return null;

  // A queued run has not started. Unknown stage names fall back to the first
  // step below, which would announce parsing that is not happening, so waiting
  // for capacity is reported as itself and claims no step and no progress.
  const queued = currentStage === QUEUED_STAGE;
  const foundIndex = currentStage
    ? steps.findIndex((step) => step.key === currentStage)
    : -1;
  const activeIndex = foundIndex >= 0 ? foundIndex : 0;
  const activeStep = steps[activeIndex];
  const hasCount = !queued && !!progress && progress.total > 0;

  // A run lasts tens of seconds, so the wait is determinate: stage position
  // plus the active stage's own count. The bar advances with real work rather
  // than looping, which a spinner alone cannot express.
  const withinStage = hasCount ? progress.completed / progress.total : 0;
  const fraction = queued ? 0 : Math.min(1, (activeIndex + withinStage) / steps.length);

  return (
    <div className="min-w-0">
      <div
        role="status"
        aria-live="polite"
        aria-atomic="true"
        className="flex min-w-0 items-center gap-2 text-xs"
      >
      <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-muted-foreground" />
      <span className="min-w-0 truncate font-medium text-foreground">
        {queued ? "Waiting for capacity" : activeStep?.label ?? "Starting analysis"}
      </span>
      {!queued && (
        <span className="shrink-0 tabular-nums text-muted-foreground">
          {activeIndex + 1} of {steps.length}
        </span>
      )}
        {hasCount && (
          <span className="shrink-0 tabular-nums text-muted-foreground">
            · {progress.completed}/{progress.total}
          </span>
        )}
        {/* Hidden from assistive technology on purpose: a number changing every
            second inside a live region is announced every second. The stage name
            beside it already reports what is happening. */}
        <span
          aria-hidden="true"
          className="ml-auto shrink-0 tabular-nums text-muted-foreground"
        >
          {formatElapsed(elapsed)}
        </span>
      </div>
      {/* The text above already announces progress, so the bar is decorative
          to assistive technology rather than a second source of chatter. */}
      <div
        aria-hidden="true"
        className="mt-2 h-0.5 w-full overflow-hidden rounded-full bg-border"
      >
        <div
          className={cn(
            "h-full rounded-full bg-foreground",
            "transition-[width] duration-base ease-enter motion-reduce:transition-none",
          )}
          style={{ width: `${Math.round(fraction * 100)}%` }}
        />
      </div>
    </div>
  );
}

/**
 * Milliseconds since `busy` became true, ticking once a second.
 *
 * Read from the clock rather than counted from ticks: a background tab throttles
 * timers, and a counter would quietly under-report exactly when someone leaves a
 * long analysis running and comes back to check on it.
 */
function useElapsedWhile(busy: boolean): number {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    if (!busy) {
      setElapsed(0);
      return;
    }
    const startedAt = Date.now();
    setElapsed(0);
    const timer = window.setInterval(() => setElapsed(Date.now() - startedAt), 1000);
    return () => window.clearInterval(timer);
  }, [busy]);

  return elapsed;
}
