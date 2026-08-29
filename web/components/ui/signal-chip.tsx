import type { ReactNode } from "react";

import { ToneDot } from "@/components/ui/tone-dot";
import type { Tone } from "@/lib/tone";
import { cn } from "@/lib/utils";

/**
 * One verdict, marked by a dot.
 *
 * The quietest signal the tone scale offers, and the right one when a row carries several:
 * a reader comparing four counts is not hunting for one verdict, so four tints would paint
 * the row without helping them.
 *
 * Lived in Scout as a local component while three other tools hand-rolled their own
 * version of the same row - one with tinted pills, one with plain muted text, one with
 * cells - so one idea had four appearances across four tools.
 */
export function SignalChip({
  tone,
  children,
  className,
}: {
  tone: Tone;
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex h-5 items-center gap-1.5 whitespace-nowrap text-[11px] font-medium text-foreground",
        className,
      )}
    >
      <ToneDot tone={tone} />
      {children}
    </span>
  );
}
