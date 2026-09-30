import type { ReactNode } from "react";
import { ChevronDown } from "lucide-react";

import { cn } from "@/lib/utils";

/**
 * The clickable line of an inline `<details>`: the suite's chevron, then its label.
 *
 * Every other disclosure turns a Lucide chevron, and these were the ones still drawing the
 * browser's own triangle - a marker in a different weight, colour and position on each
 * platform, beside controls the suite otherwise styles. The chevron leads, as it does on
 * `DisclosureRow` ("Rubric requirement", "Justification", "Search queries"): one position for
 * every text-line disclosure. Only a full-width card or row puts it at its right edge.
 *
 * The chevron turns off the parent's open state directly, so a caller needs no group name.
 */
export function DisclosureSummary({ children, className }: {
  children: ReactNode;
  /** Type, colour, spacing and focus treatment; the marker and the chevron belong here. */
  className?: string;
}) {
  return (
    <summary className={cn("flex cursor-pointer list-none items-center gap-2 [&::-webkit-details-marker]:hidden", className)}>
      <ChevronDown
        aria-hidden="true"
        className="h-3.5 w-3.5 shrink-0 text-muted-foreground transition-transform duration-base motion-reduce:transition-none [details[open]>summary>&]:rotate-180"
      />
      <span className="min-w-0">{children}</span>
    </summary>
  );
}
