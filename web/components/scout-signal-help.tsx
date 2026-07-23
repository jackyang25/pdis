"use client";

import { useState } from "react";
import { CircleHelp } from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";

export type ScoutSignalTopic =
  | "relationships"
  | "grounding"
  | "alignment"
  | "precedent";

const TOPICS: Record<
  ScoutSignalTopic,
  { title: string; summary: string; detail: string }
> = {
  relationships: {
    title: "Evidence relationships",
    summary: "How each external insight relates to the document target. The numbers count insights, not sources.",
    detail: "Conflicts means an insight contradicts the target. Adds context is relevant but neither proves nor disputes it. Supports means it reinforces the target. Unrelated does not meaningfully bear on it.",
  },
  grounding: {
    title: "Evidence · Grounding",
    summary: "The overall assessment of how well external evidence justifies the document target.",
    detail: "The source count is the evidence selected for this assessment; it does not need to equal the relationship counts.",
  },
  alignment: {
    title: "Evidence · Quantitative calibration",
    summary: "A numeric document claim compared only with source-quoted, claim-compatible, deduplicated measurements.",
    detail: "The count shows how many validated comparators meet the target. Distribution statistics describe this selected cohort only; they are not confidence intervals or forecasts. Not calculated means no numeric target with valid document lineage was available.",
  },
  precedent: {
    title: "Precedent",
    summary: "Two separate signals: how directly prior work matches the target, and what outcome that work reported.",
    detail: "Coverage is Direct, Adjacent, None found, or Unknown. Outcome is Favorable, Mixed, Unfavorable, or Unknown.",
  },
};

export function ScoutSignalLabel({
  topic,
  children,
  className,
}: {
  topic: ScoutSignalTopic;
  children: React.ReactNode;
  className?: string;
}) {
  const help = TOPICS[topic];
  const [open, setOpen] = useState(false);
  return (
    <span className={cn("inline-flex items-center gap-1", className)}>
      {children}
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <button
            type="button"
            aria-label={`About ${help.title}`}
            onClick={(event) => {
              event.preventDefault();
              event.stopPropagation();
              setOpen((current) => !current);
            }}
            onPointerDown={(event) => event.stopPropagation()}
            onKeyDown={(event) => event.stopPropagation()}
            className="inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-muted-foreground/55 transition-colors hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/20"
          >
            <CircleHelp className="h-3 w-3" />
          </button>
        </PopoverTrigger>
        <PopoverContent
          align="start"
          sideOffset={6}
          className="w-[min(320px,calc(100vw-32px))] p-3"
          onClick={(event) => event.stopPropagation()}
        >
          <h3 className="text-xs font-semibold text-foreground">{help.title}</h3>
          <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">
            {help.summary}
          </p>
          <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground/80">
            {help.detail}
          </p>
        </PopoverContent>
      </Popover>
    </span>
  );
}

export function ScoutSignalHelp() {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          className="inline-flex h-8 items-center gap-1.5 rounded-md px-2 text-xs font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/20"
        >
          <CircleHelp className="h-3.5 w-3.5" />
          How to read
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-[min(360px,calc(100vw-32px))]">
        <div>
          <h3 className="text-sm font-semibold text-foreground">How to read Scout signals</h3>
          <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">
            These columns answer different questions and should not be combined into one grade.
          </p>
        </div>
        <div className="mt-4 space-y-3.5">
          {(Object.keys(TOPICS) as ScoutSignalTopic[]).map((topic) => {
            const help = TOPICS[topic];
            return (
              <section key={topic} className="border-t border-border/70 pt-3 first:border-t-0 first:pt-0">
                <h4 className="text-xs font-semibold text-foreground">{help.title}</h4>
                <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">
                  {help.summary}
                </p>
                <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground/80">
                  {help.detail}
                </p>
              </section>
            );
          })}
        </div>
      </PopoverContent>
    </Popover>
  );
}
