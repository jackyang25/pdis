import * as React from "react";
import { cn } from "@/lib/utils";

/**
 * Curated semantic names for the bespoke PDIS icon pack. The source SVGs stay
 * untouched in public/icons/pdis; CSS masking lets them inherit currentColor.
 * Add a mapping here before using another pack icon in product UI.
 */
export const PDIS_ICON_PATHS = {
  inspector: "Outline/Files/Book-check.svg",
  aligner: "Outline/Interface/Exchange.svg",
  scout: "Outline/Devices/Binocular.svg",
  bouncer: "Outline/Status/Shield.svg",
  chunker: "Outline/Interface/Stack.svg",
  searcher: "Outline/Interface/Search.svg",
  evaluator: "Outline/Status/Checked-box.svg",
  roadmap: "Outline/Navigation/Map-location.svg",
  "executive-summary": "Outline/Files/Document.svg",
  chat: "Outline/Communication/Chat.svg",
} as const;

export type PdisIconName = keyof typeof PDIS_ICON_PATHS;

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
