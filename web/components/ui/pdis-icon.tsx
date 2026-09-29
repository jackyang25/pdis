import * as React from "react";
import { MaskedIcon } from "@/components/ui/masked-icon";
import { PDIS_ICON_PATHS, type PdisIconName } from "@/lib/pdis-icon-paths";

/**
 * Product identity icons from the PDIS Freehand pack.
 *
 * The paths are data and live in `lib/pdis-icon-paths.ts`; drawing them in `currentColor`
 * is `MaskedIcon`'s job. Re-exported so callers keep one import. Source SVGs remain
 * untouched in public/icons/pdis/freehand.
 */
export {
  PDIS_ICON_PATHS,
  type PdisIconName,
} from "@/lib/pdis-icon-paths";

type Props = Omit<React.HTMLAttributes<HTMLSpanElement>, "children"> & {
  name: PdisIconName;
};

export function PdisIcon({ name, ...props }: Props) {
  return <MaskedIcon src={`/icons/pdis/${PDIS_ICON_PATHS[name]}`} {...props} />;
}
