"use client";

import type { ReactNode } from "react";
import { ChartNoAxesColumn } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Popover, PopoverTrigger } from "@/components/ui/popover";
import { HelpHeading, HelpPopoverContent } from "./help-content";

/**
 * How the run came out, behind one button in the header.
 *
 * It was a line of its own under the run's name, and the two said overlapping things:
 * "36 fields · 1,491 insights" above "31 of 36 fields stated a target". A reader met two
 * sentences of figures before reaching a single result, and had to work out that the two
 * `36`s were the same 36.
 *
 * So the header states the run's **scope** - what was examined, in one line - and this
 * holds every figure about how it **came out**. Behind a click, which is the trade: the
 * outcome is one action away rather than in front of you. What it buys is that the header
 * is one line in every tool, and the figures get room to be read as figures instead of
 * being compressed into a strip.
 *
 * The affordance is the one beside it. `How to read` explains the vocabulary of the view
 * you are on; this reports the numbers of the run you are in. Same button, same place,
 * two different questions - so a reader learns one gesture.
 */
export function ResultMetrics({
  title,
  intro,
  children,
}: {
  /** What these figures are of. The run, named the way its card names it. */
  title: string;
  /** What the figures are counting, and anything that does not add up as it looks. */
  intro: string;
  children: ReactNode;
}) {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button type="button" variant="quiet" size="toolbar">
          <ChartNoAxesColumn aria-hidden="true" />
          Metrics
        </Button>
      </PopoverTrigger>
      <HelpPopoverContent align="end" aria-label="Result metrics" className="w-[min(400px,calc(100vw-24px))]">
        <HelpHeading>{title}</HelpHeading>
        <p className="mt-2">{intro}</p>
        <div className="mt-3.5">{children}</div>
      </HelpPopoverContent>
    </Popover>
  );
}
