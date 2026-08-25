"use client";

import * as React from "react";
import * as LabelPrimitive from "@radix-ui/react-label";
import { EYEBROW } from "@/lib/typography";
import { cn } from "@/lib/utils";

const Label = React.forwardRef<
  React.ElementRef<typeof LabelPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof LabelPrimitive.Root>
>(({ className, ...props }, ref) => (
  <LabelPrimitive.Root
    ref={ref}
    // The same shape as an eyebrow, because it is the same thing: a small capitalised label
    // over a value. This carried its own weight and letter-spacing, which is how a form field
    // and a result panel came to label themselves differently on one page.
    className={cn(EYEBROW, className)}
    {...props}
  />
));
Label.displayName = LabelPrimitive.Root.displayName;

export { Label };
