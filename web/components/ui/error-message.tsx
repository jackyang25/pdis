import { AlertCircle } from "lucide-react";

import { SURFACE_ENTRY_MOTION } from "@/lib/motion";
import { cn } from "@/lib/utils";

/**
 * A failure reported next to the thing that failed.
 *
 * Inline rather than a toast: every failure in this app belongs to a run, a
 * field, or a control, and a message that floats away from its cause cannot say
 * how to fix it. `role="alert"` means a reader who has scrolled elsewhere still
 * hears it, which is the one advantage a toast would have offered.
 *
 * Colour is never the only signal — the icon carries the meaning for readers who
 * cannot distinguish the destructive token from body text.
 */
export function ErrorMessage({
  children,
  className,
  size = "sm",
}: {
  children: React.ReactNode;
  className?: string;
  /** `xs` for dense panels beside a control, `sm` for a run or page level. */
  size?: "xs" | "sm";
}) {
  return (
    <p
      role="alert"
      className={cn(
        "flex items-start gap-1.5 text-destructive",
        size === "xs" ? "text-xs leading-5" : "text-sm",
        SURFACE_ENTRY_MOTION,
        className,
      )}
    >
      <AlertCircle
        className={cn("shrink-0", size === "xs" ? "mt-0.5 h-3.5 w-3.5" : "mt-0.5 h-4 w-4")}
        aria-hidden="true"
      />
      <span className="min-w-0">{children}</span>
    </p>
  );
}
