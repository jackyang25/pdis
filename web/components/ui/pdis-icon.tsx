import * as React from "react";
import { cn } from "@/lib/utils";

/**
 * Curated semantic names for the PDIS Freehand icon pack. The source PNGs stay
 * untouched in public/icons/pdis/freehand; CSS masking lets them inherit currentColor.
 * Add a mapping here before using another pack icon in product UI.
 */
export const PDIS_ICON_PATHS = {
  inspector: "freehand/performance-increase-clipboard--Streamline-Freehand.png",
  aligner: "freehand/business-workflow-compare--Streamline-Freehand.png",
  scout: "freehand/focus-frame-target-1--Streamline-Freehand.png",
  bouncer: "freehand/business-coaching-whistle--Streamline-Freehand.png",
  chunker: "freehand/data-transfer-document-module--Streamline-Freehand.png",
  searcher: "freehand/seo-search-graph--Streamline-Freehand.png",
  evaluator: "freehand/business-coaching-idea-jigsaw--Streamline-Freehand.png",
  roadmap: "freehand/business-workflow-project-management--Streamline-Freehand.png",
  "executive-summary": "freehand/performance-presentation-graph--Streamline-Freehand.png",
  chat: "freehand/conversation-chat--Streamline-Freehand.png",
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
