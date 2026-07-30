"use client";

import { useId, useState } from "react";
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
 * Card-shaped collapsible container. Header actions remain independent from
 * the disclosure control so an action cannot accidentally collapse the card.
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
  const [open, setOpen] = useState(defaultOpen);
  const contentId = useId();
  return (
    <section
      className={cn(
        "overflow-hidden rounded-lg border border-border bg-card",
        className,
      )}
    >
      <header className="flex flex-wrap items-center gap-3 px-5 py-[14px] sm:px-6">
        <button
          type="button"
          aria-expanded={open}
          aria-controls={contentId}
          onClick={() => setOpen((current) => !current)}
          className="min-w-0 flex-1 rounded-md py-1 text-left outline-none transition-colors hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/20 motion-reduce:transition-none"
        >
          <h2 className="text-[15px] font-semibold tracking-tight">{title}</h2>
          {subtitle && <p className="mt-0.5 text-xs text-muted-foreground">{subtitle}</p>}
        </button>
        <div className="ml-auto flex min-w-0 items-center gap-2">
          {trailing && <div className="flex min-w-0 flex-wrap items-center justify-end gap-2">{trailing}</div>}
          <button
            type="button"
            aria-expanded={open}
            aria-controls={contentId}
            aria-label={open ? `Collapse ${title}` : `Expand ${title}`}
            onClick={() => setOpen((current) => !current)}
            className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-muted-foreground outline-none transition-colors hover:bg-accent hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/20 motion-reduce:transition-none"
          >
            <ChevronDown className={cn("h-4 w-4 transition-transform duration-base motion-reduce:transition-none", open && "rotate-180")} />
          </button>
        </div>
      </header>
      <div id={contentId} hidden={!open}>
        <Separator />
        <div className={cn("px-5 py-4 sm:px-6", contentClassName)}>{children}</div>
      </div>
    </section>
  );
}
