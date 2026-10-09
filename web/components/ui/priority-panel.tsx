"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";
import { ChevronUp } from "lucide-react";

import { DocumentSourceTrace } from "@/components/document-source-trace";
import { Skeleton } from "@/components/ui/skeleton";
import { Reading } from "@/components/ui/evidence-text";
import { TRIGGER_AT_LINE_START } from "@/components/ui/provenance";
import type { PriorityFinding } from "@/lib/priorities";
import type { ReadingView } from "@/lib/priority-reading";
import { TEXT_TOGGLE } from "@/lib/typography";
import { cn } from "@/lib/utils";

/**
 * The card every tool opens with: what the result amounts to, and where to look first.
 *
 * Rendering only. What a tool's result holds arrives as `findings`, named the way the tool's
 * page names them; what to raise arrives as a model's `reading`, whose points name findings
 * by ID. Each point shows the findings it rests on from that list, so it can never describe a
 * finding differently from the row it points at, and its passages open through the same
 * source trigger every result row uses.
 *
 * The whole card is a model's reading and says so. The tool's own sections below remain the
 * full, code-ordered result; nothing here edits, re-ranks or overturns them.
 */
export function PriorityPanel({
  findings,
  reading,
  title = "Priorities",
  /**
   * Closed, like every other disclosure on the page. The count beside the title says how
   * many points there are without opening it, which is what a lede has to do.
   */
  defaultOpen = false,
}: {
  findings: PriorityFinding[];
  reading: ReadingView | undefined;
  title?: string;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const byId = useMemo(() => new Map(findings.map((finding) => [finding.id, finding])), [findings]);
  const points = reading?.state === "ready" ? reading.reading.points : [];
  return (
    // No border and no corners: this is a band in the result layout, between the tab row
    // and the toolbar, and both of those are flush.
    <section>
      <div className="flex flex-wrap items-center gap-3 px-5 py-[14px] sm:px-6">
        <p className="flex min-w-0 flex-1 items-center gap-2 text-sm">
          <PriorityGlyph />
          <span className="font-semibold text-foreground">{title}</span>
          {reading?.state === "ready" && (
            <span className="tabular-nums text-muted-foreground">{points.length}</span>
          )}
        </p>
        <button
          type="button"
          onClick={() => setOpen((current) => !current)}
          aria-expanded={open}
          aria-label={open ? `Hide ${title.toLowerCase()}` : `Show ${title.toLowerCase()}`}
          className="shrink-0 rounded-md p-1 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/20 motion-reduce:transition-none"
        >
          <ChevronUp
            className={cn(
              "h-4 w-4 transition-transform duration-base motion-reduce:transition-none",
              !open && "rotate-180",
            )}
          />
        </button>
      </div>
      {open && (
        <div className="border-t border-border px-5 py-4 sm:px-6">
          {findings.length === 0 ? (
            <p className="text-sm text-muted-foreground">This result holds no findings to read.</p>
          ) : !reading || reading.state === "loading" ? (
            // Space held so the result below does not jump when the reading lands.
            <div className="space-y-1.5" aria-label="Reading this result">
              <Skeleton className="h-3.5 w-full" />
              <Skeleton className="h-3.5 w-[88%]" />
              <Skeleton className="mt-4 h-3.5 w-[60%]" />
              <Skeleton className="h-3.5 w-[80%]" />
            </div>
          ) : reading.state === "failed" ? (
            // Said quietly rather than swallowed: a skeleton followed by nothing is
            // indistinguishable from a tool that has no card.
            <p className="text-xs leading-5 text-muted-foreground">
              No priorities for this run. {reading.reason}{" "}
              <button type="button" onClick={reading.retry} className={TEXT_TOGGLE}>
                Try again
              </button>
            </p>
          ) : (
            <>
              <PrioritySummary key={reading.reading.summary} summary={reading.reading.summary} />
              {points.length > 0 ? (
                <ol className="space-y-4">
                  {points.map((point) => (
                    <PriorityPointRow
                      key={point.title}
                      title={point.title}
                      statement={point.statement}
                      findings={point.finding_ids.flatMap((id) => byId.get(id) ?? [])}
                    />
                  ))}
                </ol>
              ) : (
                <p className="text-sm text-muted-foreground">
                  Nothing in this result needs attention first.
                </p>
              )}
            </>
          )}
          <p className="mt-4 border-t border-border pt-2.5 text-xs leading-5 text-muted-foreground">
            Read by AI from every finding in this result, so the selection and order are the
            AI&apos;s. Each point names the findings it rests on; the result below is unchanged.
          </p>
        </div>
      )}
    </section>
  );
}

function PriorityPointRow({
  title,
  statement,
  findings,
}: {
  title: string;
  statement: string;
  findings: PriorityFinding[];
}) {
  const blockIds = [...new Set(findings.flatMap((finding) => finding.blockIds))];
  return (
    <li className="text-sm leading-6">
      <p className="font-medium">{title}</p>
      <Reading size="prominent">{statement}</Reading>
      {/* The findings the point rests on, as the tool's page names them: the tool's words,
          so full contrast for the name and muted for where it sits and what was decided.
          Name and verdicts only, the same two lines for every tool. The document's own words
          are one click away in the source trigger below and on the row itself; quoted here,
          a raw target ran to several lines and only one tool had any. */}
      <ul className="mt-2 space-y-1.5 border-l border-border pl-3">
        {findings.map((finding) => (
          <li key={finding.id} className="text-xs leading-5">
            <p className="line-clamp-2 text-foreground">{finding.subject}</p>
            <p className="text-muted-foreground">
              {[finding.group, ...finding.verdicts].filter(Boolean).join(" · ")}
            </p>
          </li>
        ))}
      </ul>
      {blockIds.length > 0 && (
        <div className={cn("mt-1.5", TRIGGER_AT_LINE_START)}>
          <DocumentSourceTrace blockIds={blockIds} />
        </div>
      )}
    </li>
  );
}

/** Presentation only: retain the complete authored summary, never generate a shorter one. */
function PrioritySummary({ summary }: { summary: string }) {
  const id = useId();
  const content = useRef<HTMLDivElement>(null);
  const [expanded, setExpanded] = useState(false);
  const [overflows, setOverflows] = useState(false);

  useEffect(() => {
    const element = content.current;
    if (!element || expanded) return;
    const measure = () => setOverflows(element.scrollHeight > element.clientHeight + 1);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [expanded]);

  return <div className="mb-4 max-w-prose">
    <div ref={content} id={id} className={expanded ? undefined : "max-h-24 overflow-hidden"}>
      <Reading size="body" className="whitespace-pre-line">{summary}</Reading>
    </div>
    {(overflows || expanded) && <button type="button" aria-expanded={expanded} aria-controls={id}
      onClick={() => setExpanded(value => !value)}
      className={cn("mt-2 text-xs", TEXT_TOGGLE)}>
      {expanded ? "Show less summary" : "Read full summary"}
    </button>}
  </div>;
}

/**
 * The one glyph, declared here so the tools cannot drift apart on it.
 *
 * `lucide-react`'s Sparkles, inlined so the marker for "a model wrote this" has exactly one
 * definition.
 */
function PriorityGlyph() {
  return (
    <svg
      aria-hidden
      viewBox="0 0 24 24"
      className="h-4 w-4 shrink-0 fill-none stroke-current stroke-2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3Z" />
      <path d="M5 3v4M19 17v4M3 5h4M17 19h4" />
    </svg>
  );
}
