import * as React from "react";
import { cn } from "@/lib/utils";

type Props = Omit<React.HTMLAttributes<HTMLSpanElement>, "children"> & {
  /** Public path of the SVG, from the site root. */
  src: string;
};

/**
 * An SVG drawn in `currentColor`, by using its shape as a mask over a filled box.
 *
 * Shared by the product's own icons and by the marks of products it links to, because
 * both need the same thing: a file kept exactly as its source supplied it, drawn in
 * whatever colour the surface calls for. Only the shape of the file is read, so a colour
 * baked into it - a brand's own fill - never reaches the page.
 */
export function MaskedIcon({ src, className, style, ...props }: Props) {
  const url = src
    .split("/")
    .map((segment) => encodeURIComponent(segment))
    .join("/");
  const labelled = props["aria-label"] != null;

  return (
    <span
      {...props}
      aria-hidden={labelled ? undefined : true}
      role={labelled ? "img" : undefined}
      className={cn("inline-block shrink-0 bg-current", className)}
      style={{
        WebkitMaskImage: `url("${url}")`,
        maskImage: `url("${url}")`,
        WebkitMaskPosition: "center",
        maskPosition: "center",
        WebkitMaskRepeat: "no-repeat",
        maskRepeat: "no-repeat",
        WebkitMaskSize: "contain",
        maskSize: "contain",
        ...style,
      }}
    />
  );
}
