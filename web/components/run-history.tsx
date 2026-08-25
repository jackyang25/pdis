"use client";

import { Check, ChevronDown, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import type { StoredResult } from "@/lib/session";
import { cn } from "@/lib/utils";

type Props<TResult> = {
  runs: StoredResult<TResult>[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onRemove: (id: string) => void;
  /** How one run is named, since only the tool knows what identifies its work. */
  label: (result: TResult) => string;
};

function when(createdAt: string): string {
  const at = new Date(createdAt);
  if (Number.isNaN(at.getTime())) return "";
  return at.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

/**
 * Switch between the runs a tool is holding for this session.
 *
 * Hidden entirely for a single run: a picker offering one choice is noise, and
 * this only earns its place once a second run exists to compare against.
 *
 * Removing is the only way back under the limit, so it lives here rather than
 * somewhere a user would have to find — the limit refuses new runs instead of
 * discarding old ones, which would otherwise be a dead end.
 */
export function RunHistory<TResult>({
  runs,
  selectedId,
  onSelect,
  onRemove,
  label,
}: Props<TResult>) {
  if (runs.length < 2) return null;

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="sm">
          {runs.length} runs
          <ChevronDown className="ml-1 h-3 w-3" aria-hidden="true" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-72 p-1">
        <ul className="space-y-0.5">
          {runs.map((run) => (
            <li
              key={run.id}
              className={cn(
                "flex items-center gap-1",
                run.id === selectedId && "rounded-sm bg-foreground/[0.07]",
              )}
            >
              <button
                type="button"
                onClick={() => onSelect(run.id)}
                aria-current={run.id === selectedId ? "true" : undefined}
                className="flex min-w-0 flex-1 items-center gap-2 rounded-sm px-2 py-1.5 text-left text-xs transition-colors hover:bg-foreground/[0.045] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/20 motion-reduce:transition-none"
              >
                <Check
                  className={cn(
                    "h-3 w-3 shrink-0",
                    run.id === selectedId ? "text-foreground" : "invisible",
                  )}
                  aria-hidden="true"
                />
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-medium text-foreground">
                    {label(run.result)}
                  </span>
                  <span className="block text-[10px] text-muted-foreground">
                    {when(run.created_at)}
                  </span>
                </span>
              </button>
              <button
                type="button"
                onClick={() => onRemove(run.id)}
                aria-label={`Remove ${label(run.result)}`}
                className="rounded-sm p-1 text-muted-foreground transition-colors hover:bg-foreground/[0.045] hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/20 motion-reduce:transition-none"
              >
                <X className="h-3 w-3" aria-hidden="true" />
              </button>
            </li>
          ))}
        </ul>
      </PopoverContent>
    </Popover>
  );
}
