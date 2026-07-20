"use client";

import { ChevronDown } from "lucide-react";
import { Separator } from "./ui/separator";
import { cn } from "@/lib/utils";

type Props = {
  title: string;
  subtitle?: React.ReactNode;
  trailing?: React.ReactNode;
  defaultOpen?: boolean;
  children: React.ReactNode;
  className?: string;
  contentClassName?: string;
};

/**
 * Card-shaped collapsible container. Header is always visible (so the user
 * sees what's there); body collapses on click. Uses native <details> for
 * accessibility and persistence-free open state.
 */
export function CollapsibleCard({
  title,
  subtitle,
  trailing,
  defaultOpen = true,
  children,
  className,
  contentClassName,
}: Props) {
  return (
    <details
      open={defaultOpen}
      className={cn(
        "group overflow-hidden rounded-lg border border-border bg-card [&_summary]:list-none",
        className,
      )}
    >
      <summary className="flex cursor-pointer flex-wrap items-center justify-between gap-4 px-5 py-[18px] transition-colors hover:bg-muted/25 sm:px-6">
        <div className="min-w-0 flex-1">
          <h2 className="text-[15px] font-semibold tracking-tight">{title}</h2>
          {subtitle && (
            <p className="mt-0.5 text-xs text-muted-foreground">{subtitle}</p>
          )}
        </div>
        <div className="ml-auto flex items-center gap-3">
          <div className="flex items-center gap-2" onClick={(event) => event.stopPropagation()}>
            {trailing}
          </div>
          <ChevronDown className="h-4 w-4 text-muted-foreground transition-transform group-open:rotate-180" />
        </div>
      </summary>
      <Separator />
      <div className={cn("px-5 py-4 sm:px-6", contentClassName)}>{children}</div>
    </details>
  );
}
