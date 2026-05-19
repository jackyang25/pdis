"use client";

import { useEffect, useState } from "react";
import { Check, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

type Props = {
  steps: string[];
  /** Cycles through steps to indicate progress while the backend is running. */
  busy: boolean;
  /** Approximate seconds per step. Visual only — backend has no streaming. */
  cadenceSec?: number;
};

export function ProgressSteps({ steps, busy, cadenceSec = 8 }: Props) {
  const [activeIndex, setActiveIndex] = useState(0);

  useEffect(() => {
    if (!busy) {
      setActiveIndex(0);
      return;
    }
    const interval = setInterval(() => {
      setActiveIndex((i) => Math.min(i + 1, steps.length - 1));
    }, cadenceSec * 1000);
    return () => clearInterval(interval);
  }, [busy, cadenceSec, steps.length]);

  if (!busy) return null;

  return (
    <ol className="flex flex-col gap-2 rounded-md border border-border bg-secondary/30 p-4">
      {steps.map((label, idx) => {
        const isDone = idx < activeIndex;
        const isActive = idx === activeIndex;
        return (
          <li key={label} className="flex items-center gap-3 text-sm">
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
              {label}
            </span>
          </li>
        );
      })}
    </ol>
  );
}
