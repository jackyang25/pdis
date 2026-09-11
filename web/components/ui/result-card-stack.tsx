import type { ReactNode } from "react";

/** Equal spacing between peer result cards, independent of tool-specific content. */
export function ResultCardStack({ children }: { children: ReactNode }) {
  return <div className="space-y-3">{children}</div>;
}
