import type { ComponentPropsWithoutRef, ReactNode } from "react";
import { PopoverContent } from "./popover";
import { cn } from "@/lib/utils";

/** Help shares a reading scale and surface; callers own its meaning and trigger. */
export function HelpPopoverContent({ className, ...props }: ComponentPropsWithoutRef<typeof PopoverContent>) {
  return <PopoverContent {...props} className={cn(
    "w-[min(360px,calc(100vw-24px))] break-words text-xs leading-relaxed text-muted-foreground",
    className,
  )} />;
}

export function HelpHeading({ children }: { children: ReactNode }) {
  return <h3 className="font-sans text-sm font-semibold leading-snug text-foreground">{children}</h3>;
}

export function HelpSection({ title, children }: { title: string; children: ReactNode }) {
  return <section className="space-y-2">
    <h4 className="font-sans text-xs font-semibold text-foreground">{title}</h4>
    {children}
  </section>;
}
