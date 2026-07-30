import { cn } from "@/lib/utils";

/**
 * A placeholder in the shape of content that is arriving.
 *
 * Only for waits where the shape is known in advance — a result section, a
 * fetched table. A tool run reports named stages instead, because a shimmer
 * cannot say which of five stages is executing. This is the one place
 * `animate-shimmer` is permitted.
 */
export function Skeleton({
  className,
  lines = 1,
}: {
  className?: string;
  /** Renders a stack of decreasing-width bars, as prose would occupy. */
  lines?: number;
}) {
  if (lines > 1) {
    return (
      <div className="space-y-2" aria-hidden="true">
        {Array.from({ length: lines }, (_, index) => (
          <Bar
            key={index}
            className={cn(
              index === lines - 1 ? "w-3/5" : "w-full",
              className,
            )}
          />
        ))}
      </div>
    );
  }
  return <Bar className={className} aria-hidden="true" />;
}

function Bar({ className, ...props }: React.ComponentPropsWithoutRef<"div">) {
  return (
    <div
      className={cn(
        "relative h-3 overflow-hidden rounded bg-muted",
        // The sweep is the only animation; the bar itself never pulses, so a
        // reduced-motion reader still sees the shape without movement.
        // Animation and its opt-out travel in one string, so neither can be
        // moved or copied without the other.
        "after:absolute after:inset-0 after:-translate-x-full after:animate-shimmer motion-reduce:after:hidden",
        "after:bg-gradient-to-r after:from-transparent after:via-foreground/[0.06] after:to-transparent",
        className,
      )}
      {...props}
    />
  );
}
