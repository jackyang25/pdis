import * as React from "react";
import { SURFACE } from "@/lib/surface";
import { cn } from "@/lib/utils";

export type SegmentedOption<T extends string> = {
  value: T;
  label: string;
  /** Decorative: the label names the option. */
  icon?: React.ReactNode;
};

type Props<T extends string> = {
  options: readonly SegmentedOption<T>[];
  value: T;
  onChange: (value: T) => void;
  /** What is being chosen, for a screen reader: the group has no visible heading. */
  "aria-label": string;
  className?: string;
};

/**
 * One choice among a few views of the same thing: a recessed track, and the chosen option
 * raised out of it.
 *
 * A toggle-button group, not an ARIA tab set. Each option swaps one view in place - the
 * tools a page lists, the diagram a canvas draws - rather than revealing a sibling panel, so
 * `aria-pressed` says what a screen reader can act on without promising a tabpanel. Tabs
 * (`ui/tabs`) are for sibling panels, and look it.
 *
 * The track is the recessed tint with no edge of its own, so it stays light; its outer edge
 * is the edge of whatever column it sits in, so nothing sticks out past the text above it; and
 * the chosen option is raised with `shadow-raised`, the height of a card, so the control and
 * the content it filters share one language. Radii nest: a 12px track, 4px of padding, 8px
 * options. A track with more options than fit scrolls sideways rather than wrapping, because a
 * wrapped track is two tracks.
 */
export function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
  "aria-label": label,
  className,
}: Props<T>) {
  return (
    <div
      role="group"
      aria-label={label}
      className={cn(
        "inline-flex max-w-full gap-0.5 overflow-x-auto rounded-lg p-1",
        SURFACE.recessed,
        className,
      )}
    >
      {options.map((option) => {
        const selected = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            aria-pressed={selected}
            onClick={() => onChange(option.value)}
            className={cn(
              "inline-flex h-7 shrink-0 items-center gap-1.5 rounded-sm px-3 text-xs font-medium transition-[color,background-color,box-shadow] duration-fast ease-enter focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring/25 motion-reduce:transition-none",
              selected
                ? "bg-card text-foreground shadow-raised"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {option.icon}
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
