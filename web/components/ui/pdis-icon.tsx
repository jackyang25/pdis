import * as React from "react";
import { cn } from "@/lib/utils";
import { PDIS_ICON_PATHS, type PdisIconName } from "@/lib/pdis-icon-paths";

/**
 * Product identity icons from the PDIS Freehand pack.
 *
 * The paths are data and live in `lib/pdis-icon-paths.ts`; this file owns only the
 * masking that lets an SVG inherit `currentColor`. Re-exported so callers keep one
 * import. Source SVGs remain untouched in public/icons/pdis/freehand.
 */
export {
  PDIS_ICON_PATHS,
  type PdisIconName,
} from "@/lib/pdis-icon-paths";

type Props = Omit<React.HTMLAttributes<HTMLSpanElement>, "children"> & {
  name: PdisIconName;
};

export function PdisIcon({ name, className, style, ...props }: Props) {
  const path = PDIS_ICON_PATHS[name]
    .split("/")
    .map((segment) => encodeURIComponent(segment))
    .join("/");
  const url = `/icons/pdis/${path}`;
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
