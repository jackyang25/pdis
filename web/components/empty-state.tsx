import { AlertTriangle, CheckCircle2 } from "lucide-react";

import { TONE_TEXT } from "@/lib/tone";
import { cn } from "@/lib/utils";

/**
 * Nothing to show, and why.
 *
 * One component because four places had grown their own box for one idea, differing on
 * three axes at once - dashed or solid border, one line or a heading with a body, an icon
 * or none - none of which marked a difference in what they were saying. The fifth place
 * that needed one would have been a fifth box.
 *
 * The tone is the part that carries meaning, and it is deliberately named for the reader's
 * question rather than for a colour. "There is nothing here" and "we checked and found
 * nothing" are different answers, and a reader who cannot tell them apart cannot tell a
 * clean document from an unread one.
 *
 *     absence  nothing has been produced yet, or nothing was retained. No judgment.
 *     clear    something ran, looked, and found nothing to report. Good news.
 *     unknown  something did not finish, so the absence is not an answer.
 *
 * `absence` is dashed and the other two are solid, which is the same distinction again in
 * the border: a dashed box reads as a slot waiting to be filled, and a stated result is
 * not a slot.
 */
export type EmptyStateTone = "absence" | "clear" | "unknown";

const TONE_ICON = {
  clear: CheckCircle2,
  unknown: AlertTriangle,
} as const;

export function EmptyState({
  message,
  detail,
  tone = "absence",
  className,
}: {
  /** The answer, in one line. */
  message: string;
  /** Why, when the answer alone would leave a reader guessing. */
  detail?: string;
  tone?: EmptyStateTone;
  className?: string;
}) {
  const Icon = tone === "absence" ? null : TONE_ICON[tone];
  return (
    <div
      className={cn(
        "rounded-lg px-5 py-5",
        tone === "absence"
          ? "border border-dashed border-border text-center"
          : "border border-border bg-foreground/[0.045]",
        className,
      )}
    >
      <div className={cn("flex items-start gap-3", tone === "absence" && "justify-center")}>
        {Icon && (
          <Icon
            aria-hidden="true"
            className={cn(
              "mt-0.5 h-4 w-4 shrink-0",
              tone === "clear" ? TONE_TEXT.success : TONE_TEXT.warning,
            )}
          />
        )}
        <div className="min-w-0">
          <p className="text-sm font-medium text-foreground">{message}</p>
          {detail && (
            <p className="mt-1 text-xs leading-5 text-muted-foreground">{detail}</p>
          )}
        </div>
      </div>
    </div>
  );
}
