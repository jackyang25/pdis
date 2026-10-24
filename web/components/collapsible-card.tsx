"use client";

import { useId, useState } from "react";
import { ChevronDown } from "lucide-react";
import { Separator } from "./ui/separator";
import { cn } from "@/lib/utils";
import { COUNT, DISPLAY_HEADING } from "@/lib/typography";

type Props = {
  title: string;
  /** A result count belongs beside its heading, not among header actions. */
  count?: number;
  subtitle?: React.ReactNode;
  trailing?: React.ReactNode;
  /**
   * More header, below the title row and above the rule.
   *
   * Inside the header rather than at the top of the content, because a card's
   * `Separator` reads as a boundary between components: a figure row passed as content
   * sat under that line and became a second block, so the run's name and the run's
   * figures looked like two things about two subjects.
   */
  meta?: React.ReactNode;
  /**
   * Whether to rule the header off from the content.
   *
   * Off when the content opens with a band that draws its own edge - a tab row - because
   * two rules with only a row of tabs between them make the tabs a strip of their own.
   */
  separated?: boolean;
  defaultOpen?: boolean;
  /**
   * Whether the card folds at all. A run's result card does not: its title is the run's
   * name, and clicking it folded away the whole result, which no reader meant.
   */
  collapsible?: boolean;
  children: React.ReactNode;
  className?: string;
  /**
   * Content that draws its own edges - bands, rows, toolbars - and so takes no padding.
   *
   * A switch rather than a class override: an override of `px-5 py-4 sm:px-6` with `p-0`
   * kept the `sm:` padding, so from tablet width up every flush band sat 24px inside the
   * title. Two callers were each patching that differently.
   */
  flush?: boolean;
};

/**
 * Card-shaped collapsible container. Header actions remain independent from
 * the disclosure control so an action cannot accidentally collapse the card.
 */
export function CollapsibleCard({
  title,
  count,
  subtitle,
  trailing,
  meta,
  separated = true,
  defaultOpen = true,
  collapsible = true,
  children,
  className,
  flush = false,
}: Props) {
  const [expanded, setOpen] = useState(defaultOpen);
  const open = !collapsible || expanded;
  const contentId = useId();
  return (
    <section
      className={cn(
        "overflow-hidden rounded-lg bg-card shadow-raised",
        className,
      )}
    >
      <header className="px-5 py-[14px] sm:px-6">
        <div className="flex flex-wrap items-center gap-3">
        {(() => {
          const heading = (
            <>
              <h2 className={cn(DISPLAY_HEADING, "text-[15px] font-semibold")}>
                {title}
                {count !== undefined && <span className={cn("ml-2 font-sans font-normal", COUNT)}> {count}</span>}
              </h2>
              {subtitle && <p className="mt-0.5 text-xs text-muted-foreground">{subtitle}</p>}
            </>
          );
          return collapsible ? (
            <button
              type="button"
              aria-expanded={open}
              aria-controls={contentId}
              onClick={() => setOpen((current) => !current)}
              className="min-w-0 flex-1 basis-48 rounded-md py-1 text-left outline-none transition-colors hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/60 motion-reduce:transition-none"
            >
              {heading}
            </button>
          ) : (
            <div className="min-w-0 flex-1 basis-48 py-1">{heading}</div>
          );
        })()}
        <div className="ml-auto flex min-w-0 items-center gap-2">
          {trailing && <div className="flex min-w-0 flex-wrap items-center justify-end gap-1">{trailing}</div>}
          {collapsible && <button
            type="button"
            aria-expanded={open}
            aria-controls={contentId}
            aria-label={open ? `Collapse ${title}` : `Expand ${title}`}
            onClick={() => setOpen((current) => !current)}
            className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-muted-foreground outline-none transition-colors hover:bg-accent hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/60 motion-reduce:transition-none"
          >
            <ChevronDown className={cn("h-4 w-4 transition-transform duration-base motion-reduce:transition-none", open && "rotate-180")} />
          </button>}
        </div>
        </div>
        {meta && open && <div className="mt-3">{meta}</div>}
      </header>
      <div id={contentId} hidden={!open}>
        {separated && <Separator />}
        <div className={flush ? undefined : "px-5 py-4 sm:px-6"}>{children}</div>
      </div>
    </section>
  );
}
