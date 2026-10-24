"use client";

import { useId, useState } from "react";
import { usePathname } from "next/navigation";
import { Flag } from "lucide-react";

import { Button } from "@/components/ui/button";
import { HelpHeading, HelpPopoverContent } from "@/components/ui/help-content";
import { Popover, PopoverTrigger } from "@/components/ui/popover";
import { FEEDBACK_EMAIL, findingReportMailto, findingReportText, type FindingReport } from "@/lib/finding-report";
import { WORKSPACE_TOOLS } from "@/lib/tools";
import { cn } from "@/lib/utils";

/**
 * "This looks wrong": the reader's note, emailed with the finding's details.
 *
 * Emailed from the reader's own client rather than sent, because PDIS stores nothing - a
 * report has nowhere to go but the person who reads feedback. The report is shown before
 * it is sent, so a reader sees exactly what they are about to share.
 */
export function ReportFinding({ report, className }: { report: Omit<FindingReport, "tool" | "note">; className?: string }) {
  const pathname = usePathname();
  const tool = WORKSPACE_TOOLS.find((entry) => entry.href && pathname?.startsWith(entry.href))?.title ?? "PDIS";
  const [note, setNote] = useState("");
  const noteId = useId();
  const full = { ...report, tool, note };

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button type="button" variant="quiet" size="toolbar" className={cn("-ml-2.5", className)}>
          <Flag aria-hidden="true" />
          Report a problem
        </Button>
      </PopoverTrigger>
      <HelpPopoverContent align="start" aria-label="Report a problem with this finding">
        <HelpHeading>Report a problem</HelpHeading>
        <label htmlFor={noteId} className="mt-2 block text-xs text-muted-foreground">What is wrong?</label>
        <textarea
          id={noteId}
          value={note}
          onChange={(event) => setNote(event.target.value)}
          rows={3}
          className="mt-1.5 w-full resize-y rounded-md border border-input bg-card px-2.5 py-2 text-xs text-foreground outline-none focus:border-ring/60 focus:ring-2 focus:ring-ring/15"
        />
        <pre className="mt-3 max-h-40 overflow-auto whitespace-pre-wrap break-words rounded-md bg-foreground/[0.045] p-2.5 font-sans text-[11px] leading-relaxed text-muted-foreground">
          {findingReportText(full)}
        </pre>
        <div className="mt-3 flex items-center justify-between gap-3">
          <p className="min-w-0 break-words text-[11px] text-muted-foreground">Sent to {FEEDBACK_EMAIL}</p>
          <Button asChild size="toolbar" variant="outline">
            <a href={findingReportMailto(full)}>Email report</a>
          </Button>
        </div>
      </HelpPopoverContent>
    </Popover>
  );
}
