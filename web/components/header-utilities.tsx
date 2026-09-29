"use client";

import Link from "next/link";
import { BookOpen, History, MessageSquare } from "lucide-react";
import { ThemeToggle } from "@/components/theme-toggle";
import { Popover, PopoverTrigger } from "@/components/ui/popover";
import { HelpHeading, HelpPopoverContent } from "@/components/ui/help-content";
import { badgeVariants } from "@/components/ui/badge";
import { CURRENT_RELEASE } from "@/lib/releases";
import { SURFACE } from "@/lib/surface";
import { cn } from "@/lib/utils";

/** One shape for every control in the header, the theme toggle included. */
const HEADER_ACTION = cn(
  "inline-flex h-8 min-w-8 items-center justify-center gap-1.5 rounded-md px-2 text-[11px] font-medium text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/20 aria-[current=page]:bg-foreground/[0.045] aria-[current=page]:text-foreground motion-reduce:transition-none",
  SURFACE.hover,
);

export function HeaderUtilities({ pathname }: { pathname: string }) {
  return (
    <nav aria-label="Product resources" className="flex shrink-0 items-center gap-1">
      <Link href="/docs" aria-current={pathname === "/docs" ? "page" : undefined} aria-label="Documentation" className={HEADER_ACTION}>
        <BookOpen className="h-3.5 w-3.5" aria-hidden="true" />
        <span className="hidden sm:inline">Documentation</span>
      </Link>
      <Link href="/updates" aria-current={pathname === "/updates" ? "page" : undefined} aria-label={`What’s new — this version v${CURRENT_RELEASE.version}`} className={HEADER_ACTION}>
        <History className="h-3.5 w-3.5" aria-hidden="true" />
        <span className="hidden sm:inline">What’s new</span>
        {/* A tag rather than more words: set in the same size and colour as its label, the
            version read as part of the phrase - "What's new v0.4.1". */}
        <span className={cn(badgeVariants({ variant: "muted" }), "hidden tabular-nums lg:inline-flex")}>
          v{CURRENT_RELEASE.version}
        </span>
      </Link>
      <Popover>
        <PopoverTrigger asChild>
          <button type="button" aria-label="Send feedback" className={HEADER_ACTION}>
            <MessageSquare className="h-3.5 w-3.5" aria-hidden="true" />
            <span className="hidden sm:inline">Feedback</span>
          </button>
        </PopoverTrigger>
        <HelpPopoverContent align="end" aria-label="Send feedback">
          <FeedbackDetails />
        </HelpPopoverContent>
      </Popover>
      {/* The links go somewhere; the toggle changes how everything looks. A rule between them
          says they are two kinds of control rather than four of one. */}
      <span aria-hidden="true" className="mx-1.5 h-4 w-px bg-border" />
      <ThemeToggle className={HEADER_ACTION} />
    </nav>
  );
}

function FeedbackDetails() {
  return (
    <div className="space-y-3">
      <HelpHeading>Send feedback</HelpHeading>
      <p>For feedback or requests, message Jack Yang or Shyam Bhaskaran on Teams.</p>
    </div>
  );
}
