"use client";

import * as React from "react";
import * as PopoverPrimitive from "@radix-ui/react-popover";
import { cn } from "@/lib/utils";

const Popover = PopoverPrimitive.Root;
const PopoverTrigger = PopoverPrimitive.Trigger;

const PopoverContent = React.forwardRef<
  React.ElementRef<typeof PopoverPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof PopoverPrimitive.Content>
>(({ className, align = "start", sideOffset = 8, ...props }, ref) => (
  <PopoverPrimitive.Portal>
    <PopoverPrimitive.Content
      ref={ref}
      align={align}
      sideOffset={sideOffset}
      collisionPadding={12}
      className={cn(
        // Never taller than the space it has. Radix measures that and publishes it as
        // `--radix-popover-content-available-height`; without a cap a panel simply runs
        // off the bottom of the viewport, and because a popover is portalled the page
        // behind it cannot scroll to reveal the rest - the content is unreachable. The
        // help panel grew past the fold the moment its vocabulary was itemised.
        //
        // Here rather than at each call site: no popover should be able to exceed the
        // screen, and three panels had already hand-rolled their own `max-h`. A panel
        // that manages its own scrolling still can - `cn` merges, so its own overflow
        // rule wins.
        "z-50 max-h-[var(--radix-popover-content-available-height)] w-80 overflow-y-auto origin-[var(--radix-popover-content-transform-origin)] rounded-lg border border-border bg-card p-4 text-card-foreground shadow-[0_12px_36px_rgba(15,23,42,0.12)] outline-none data-[state=closed]:animate-out data-[state=open]:animate-in data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95 data-[side=bottom]:slide-in-from-top-1 data-[side=left]:slide-in-from-right-1 data-[side=right]:slide-in-from-left-1 data-[side=top]:slide-in-from-bottom-1 motion-reduce:animate-none",
        className,
      )}
      {...props}
    />
  </PopoverPrimitive.Portal>
));
PopoverContent.displayName = PopoverPrimitive.Content.displayName;

export { Popover, PopoverContent, PopoverTrigger };
