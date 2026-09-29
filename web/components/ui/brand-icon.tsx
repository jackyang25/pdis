import * as React from "react";
import { MaskedIcon } from "@/components/ui/masked-icon";
import { BRAND_MARKS, type BrandName } from "@/lib/brand-icon-paths";
import { cn } from "@/lib/utils";

type Props = {
  name: BrandName;
  className?: string;
};

/**
 * The mark of a product PDIS links out to, beside that product's name.
 *
 * In the colour its maker presents it in, and not one a caller can change: brand guidelines
 * allow a mark in its own colours or, where the brand is itself black and white, in black or
 * white - not tinted to match someone else's palette. A mark in its own colour is the file as
 * supplied; a monochrome one uses only the file's shape, black on light and white on dark.
 * Always beside the product's name, so it is decorative to a screen reader.
 */
export function BrandIcon({ name, className }: Props) {
  const mark = BRAND_MARKS[name];
  const src = `/icons/brands/${mark.file}`;
  if (mark.colour === "own") {
    // A background rather than an `<img>`, for the reason `MaskedIcon` is a mask: a styled
    // span, sized by its class, that the page treats as decoration. An `<img>` also had React
    // hoist a preload link ahead of the card that holds it.
    return (
      <span
        aria-hidden="true"
        className={cn("inline-block shrink-0 bg-contain bg-center bg-no-repeat", className)}
        style={{ backgroundImage: `url("${src}")` }}
      />
    );
  }
  return <MaskedIcon src={src} className={cn(className, "text-black dark:text-white")} />;
}
