"use client";

import { Check, Loader2 } from "lucide-react";
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
  if (!busy) return null;

  const activeIndex = currentStage
    ? Math.max(
        0,
        steps.findIndex((s) => s.key === currentStage),
      )
    : 0;

  return (
    <ol className="flex flex-col gap-2 rounded-md border border-border bg-secondary/30 p-4">
      {steps.map((step, idx) => {
        const isDone = idx < activeIndex;
        const isActive = idx === activeIndex;
        return (
          <li key={step.key} className="flex items-center gap-3 text-sm">
            <span
              className={cn(
                "flex h-5 w-5 shrink-0 items-center justify-center rounded-full border",
                isDone && "border-foreground bg-foreground text-background",
                isActive && "border-foreground",
                !isDone && !isActive && "border-border text-muted-foreground",
              )}
            >
              {isDone ? (
                <Check className="h-3 w-3" />
              ) : isActive ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : (
                <span className="text-[10px] tabular-nums">{idx + 1}</span>
              )}
            </span>
            <span
              className={cn(
                isActive ? "text-foreground" : "text-muted-foreground",
                isDone && "text-muted-foreground",
              )}
            >
              {step.label}
            </span>
            {isActive && progress && progress.total > 0 && (
              <span className="ml-auto flex items-center gap-2">
                <span className="h-1 w-16 overflow-hidden rounded-full bg-muted">
                  <span
                    className="block h-full rounded-full bg-foreground/50 transition-all"
                    style={{ width: `${(progress.completed / progress.total) * 100}%` }}
                  />
                </span>
                <span className="text-xs tabular-nums text-muted-foreground">
                  {progress.completed}/{progress.total}
                </span>
              </span>
            )}
          </li>
        );
      })}
    </ol>
  );
}
