import { Children, type ReactNode } from "react";

/** Two levels of a compact result summary. Callers own meaning, order, and visibility. */
export function ResultSummary({ signals, details }: { signals: ReactNode; details?: ReactNode }) {
  const primary = Children.toArray(signals);
  const secondary = Children.toArray(details);
  if (!primary.length && !secondary.length) return null;
  return (
    <div className="mt-2 space-y-1.5">
      {primary.length > 0 && (
        <div role="group" aria-label="Assessment signals" className="flex flex-wrap items-center gap-x-4 gap-y-1.5">
          {primary}
        </div>
      )}
      {secondary.length > 0 && (
        <div role="group" aria-label="Supporting details" className="flex flex-wrap items-center gap-x-8 gap-y-1.5 text-[11px] text-muted-foreground">
          {secondary}
        </div>
      )}
    </div>
  );
}
