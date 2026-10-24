"use client";

import { useId, useState } from "react";
import { usePathname } from "next/navigation";
import { Flag } from "lucide-react";

import { Button } from "@/components/ui/button";
import { HelpHeading, HelpPopoverContent } from "@/components/ui/help-content";
import { Popover, PopoverTrigger } from "@/components/ui/popover";
import { FEEDBACK_CONTACTS, findingReportText, type FindingReport } from "@/lib/finding-report";
import { WORKSPACE_TOOLS } from "@/lib/tools";
import { cn } from "@/lib/utils";

/**
 * "This looks wrong": the reader's note, copied with the finding's details for Teams.
 *
 * Copying rather than sending, because PDIS stores nothing - a report has nowhere to go
 * but the people who read feedback, and Teams is where they already are. The report is
 * shown before it is copied, so a reader sees exactly what they are about to share.
 */
export function ReportFinding({ report, className }: { report: Omit<FindingReport, "tool" | "note">; className?: string }) {
  const pathname = usePathname();
  const tool = WORKSPACE_TOOLS.find((entry) => entry.href && pathname?.startsWith(entry.href))?.title ?? "PDIS";
  const [note, setNote] = useState("");
  const [copied, setCopied] = useState<"idle" | "copied" | "failed">("idle");
  const noteId = useId();
  const text = findingReportText({ ...report, tool, note });

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied("copied");
    } catch {
      setCopied("failed");
    }
  }

  return (
    <Popover onOpenChange={(open) => { if (!open) setCopied("idle"); }}>
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
          onChange={(event) => { setNote(event.target.value); setCopied("idle"); }}
          rows={3}
          className="mt-1.5 w-full resize-y rounded-md border border-input bg-card px-2.5 py-2 text-xs text-foreground outline-none focus:border-ring/60 focus:ring-2 focus:ring-ring/15"
        />
        <pre className="mt-3 max-h-40 overflow-auto whitespace-pre-wrap break-words rounded-md bg-foreground/[0.045] p-2.5 font-sans text-[11px] leading-relaxed text-muted-foreground">
          {text}
        </pre>
        <div className="mt-3 flex items-center justify-between gap-3">
          <p role="status" className="text-[11px] text-muted-foreground">
            {copied === "copied"
              ? `Copied. Paste it to ${FEEDBACK_CONTACTS} on Teams.`
              : copied === "failed"
                ? "Could not copy. Select the text above and copy it."
                : `Paste it to ${FEEDBACK_CONTACTS} on Teams.`}
          </p>
          <Button type="button" size="toolbar" variant="outline" onClick={() => void copy()}>Copy report</Button>
        </div>
      </HelpPopoverContent>
    </Popover>
  );
}
