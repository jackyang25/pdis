"use client";

import { ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";

type Props = {
  summary: React.ReactNode;
  children: React.ReactNode;
  className?: string;
};

/** Native disclosure — collapsible block with chevron, consistent across tools. */
export function Disclosure({ summary, children, className }: Props) {
  return (
    <details className={cn("group", className)}>
      <summary className="flex cursor-pointer list-none items-center gap-2 text-xs font-medium uppercase tracking-wide text-muted-foreground hover:text-foreground">
        <ChevronRight className="h-3 w-3 transition-transform group-open:rotate-90" />
        {summary}
      </summary>
      <div className="mt-3">{children}</div>
    </details>
  );
}
