"use client";

import { Check, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

export type Step = { key: string; label: string };

type Props = {
  steps: Step[];
  busy: boolean;
  /** The key of the currently active step (set from a server-sent stage event). */
  currentStage: string | null;
};

export function ProgressSteps({ steps, busy, currentStage }: Props) {
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
          </li>
        );
      })}
    </ol>
  );
}
