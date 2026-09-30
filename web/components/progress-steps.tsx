"use client";

import { Check, Circle, Loader2 } from "lucide-react";
import { useEffect, useState } from "react";

import { QUEUED_STAGE } from "@/lib/api";
import { formatElapsed } from "@/lib/elapsed";
import { cn } from "@/lib/utils";

export type Step = { key: string; label: string };

type Props = {
  steps: Step[];
  busy: boolean;
  startedAt: number | null;
  /** The key of the currently active step (set from a server-sent stage event). */
  currentStage: string | null;
  /** Optional live item count for the active stage (e.g. searches completed). */
  progress?: { completed: number; total: number } | null;
};

/** At most this many stages are listed; a longer run shows the ones around its current stage. */
export const MAX_LISTED_STEPS = 5;

export type ChecklistRow =
  | { kind: "step"; step: Step; state: "done" | "active" | "pending" }
  | { kind: "summary"; state: "done" | "pending"; count: number };

/**
 * The rows a run's checklist shows: every stage when the run has few, otherwise the stage
 * before the current one, the current one and the next two, with the rest counted.
 *
 * Scout runs fifteen stages. Listed in full they made the run panel taller than the form it
 * belongs to, and the current stage was one line among fifteen.
 */
export function checklistRows(steps: Step[], activeIndex: number, queued: boolean): ChecklistRow[] {
  const stateOf = (index: number): "done" | "active" | "pending" =>
    queued || index > activeIndex ? "pending" : index < activeIndex ? "done" : "active";
  if (steps.length <= MAX_LISTED_STEPS) {
    return steps.map((step, index) => ({ kind: "step", step, state: stateOf(index) }));
  }
  const first = Math.max(0, Math.min(activeIndex - 1, steps.length - (MAX_LISTED_STEPS - 1)));
  const last = Math.min(steps.length, first + MAX_LISTED_STEPS - 1);
  const rows: ChecklistRow[] = [];
  if (first > 0) rows.push({ kind: "summary", state: queued ? "pending" : "done", count: first });
  for (let index = first; index < last; index += 1) {
    rows.push({ kind: "step", step: steps[index], state: stateOf(index) });
  }
  if (last < steps.length) rows.push({ kind: "summary", state: "pending", count: steps.length - last });
  return rows;
}

export function ProgressSteps({ steps, busy, startedAt, currentStage, progress }: Props) {
  const elapsed = useElapsedWhile(busy, startedAt);

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
  const status = queued
    ? "Waiting for capacity"
    : `${activeStep?.label ?? "Starting analysis"}, step ${activeIndex + 1} of ${steps.length}`
      + (hasCount ? `, ${progress.completed} of ${progress.total}` : "");

  // Every stage the run passes through, ticked as it finishes: the position in the run is
  // read off the list rather than off a bar, and the active stage carries its own count.
  return (
    <div className="min-w-0">
      <p role="status" aria-live="polite" aria-atomic="true" className="sr-only">{status}</p>
      <ol aria-hidden="true" className="space-y-1 text-xs">
        {checklistRows(steps, activeIndex, queued).map((row) => (
          <li
            key={row.kind === "step" ? row.step.key : `${row.state}-summary`}
            className={cn(
              "flex min-w-0 items-center gap-2 transition-colors duration-base motion-reduce:transition-none",
              row.state === "active" ? "font-medium text-foreground" : row.state === "done" ? "text-muted-foreground" : "text-muted-foreground/70",
            )}
          >
            <StepIcon state={row.state} />
            <span className="min-w-0 truncate">
              {row.kind === "step"
                ? row.step.label
                : row.state === "done" ? `${row.count} earlier ${row.count === 1 ? "step" : "steps"} done` : `${row.count} more to go`}
            </span>
            {row.kind === "step" && row.state === "active" && hasCount && (
              <span className="shrink-0 font-normal tabular-nums text-muted-foreground">
                {progress.completed}/{progress.total}
              </span>
            )}
          </li>
        ))}
      </ol>
      <p aria-hidden="true" className="mt-2 flex items-center gap-1.5 text-[11px] tabular-nums text-muted-foreground">
        {queued ? (
          <>
            <Loader2 className="h-3 w-3 shrink-0 animate-spin" />
            Waiting for capacity
          </>
        ) : (
          `${activeIndex + 1} of ${steps.length}`
        )}
        <span aria-hidden="true">·</span>
        {formatElapsed(elapsed)}
      </p>
    </div>
  );
}

function StepIcon({ state }: { state: "done" | "active" | "pending" }) {
  if (state === "done") return <Check aria-hidden="true" className="h-3.5 w-3.5 shrink-0" />;
  // Keeps turning under reduced motion: its movement is the status.
  if (state === "active") return <Loader2 aria-hidden="true" className="h-3.5 w-3.5 shrink-0 animate-spin" />;
  return <Circle aria-hidden="true" className="h-3 w-3 shrink-0 mx-px text-muted-foreground/40" />;
}

/**
 * Milliseconds since the session began processing, ticking once a second.
 *
 * Read from the clock rather than counted from ticks: a background tab throttles
 * timers, and a counter would quietly under-report exactly when someone leaves a
 * long analysis running and comes back to check on it.
 */
function useElapsedWhile(busy: boolean, startedAt: number | null): number {
  const [elapsed, setElapsed] = useState(() =>
    busy && startedAt !== null ? Math.max(0, Date.now() - startedAt) : 0,
  );

  useEffect(() => {
    if (!busy || startedAt === null) {
      setElapsed(0);
      return;
    }
    const update = () => setElapsed(Math.max(0, Date.now() - startedAt));
    update();
    const timer = window.setInterval(update, 1000);
    return () => window.clearInterval(timer);
  }, [busy, startedAt]);

  return elapsed;
}
