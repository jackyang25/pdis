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
}: Props) {
  return (
    <details
      open={defaultOpen}
      className={cn(
        "group rounded-lg border border-border bg-card [&_summary]:list-none",
        className,
      )}
    >
      <summary className="flex cursor-pointer items-center justify-between gap-4 px-6 py-4">
        <div className="flex flex-col gap-0.5">
          <h2 className="text-sm font-semibold">{title}</h2>
          {subtitle && (
            <p className="text-xs text-muted-foreground">{subtitle}</p>
          )}
        </div>
        <div className="flex items-center gap-3">
          {trailing}
          <ChevronDown className="h-4 w-4 text-muted-foreground transition-transform group-open:rotate-180" />
        </div>
      </summary>
      <Separator />
      <div className="px-6 py-4">{children}</div>
    </details>
  );
}
