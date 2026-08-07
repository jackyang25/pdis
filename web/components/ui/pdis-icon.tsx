import * as React from "react";
import { cn } from "@/lib/utils";

/**
 * Product identity icons from the PDIS Freehand pack.
 *
 * Keep this map limited to tools and named agents. Navigation, actions, status,
 * file types, and other interface grammar use Lucide so the two visual systems
 * never compete at the same semantic layer. Source SVGs remain untouched in
 * public/icons/pdis/freehand; masking lets them inherit currentColor.
 */
export const PDIS_ICON_PATHS = {
  // Native workspace tools
  inspector: "freehand/form-edition-clipboard-check--Streamline-Freehand.svg",
  aligner: "freehand/business-workflow-compare--Streamline-Freehand.svg",
  scout: "freehand/hierarchy-web--Streamline-Freehand.svg",
  expert: "freehand/human-resources-rating-man--Streamline-Freehand.svg",
  chunker: "freehand/data-transfer-document-module--Streamline-Freehand.svg",
  searcher: "freehand/search-magnifier--Streamline-Freehand.svg",

  // External workflow identities
  evaluator: "freehand/business-cash-scale-balance--Streamline-Freehand.svg",
  roadmap: "freehand/business-workflow-project-management--Streamline-Freehand.svg",
  "executive-summary": "freehand/office-file-text--Streamline-Freehand.svg",
  "stage-gate": "freehand/task-list-clipboard-clock--Streamline-Freehand.svg",

  // Named workspace agent
  chat: "freehand/help-headphones-customer-support-human--Streamline-Freehand.svg",
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
