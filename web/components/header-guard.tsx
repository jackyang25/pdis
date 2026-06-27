"use client";

import { useHeaderStore, isHeaderComplete } from "@/lib/store";

/**
 * Provides the current header + a `ready` flag (all of org/source/intervention
 * selected). It no longer blocks the page — the header is only required to RUN,
 * not to view the page or import a saved result. Callers gate the Run action on
 * `ready`.
 */
export function HeaderGuard({
  children,
}: {
  children: (
    header: ReturnType<typeof useHeaderStore.getState>["header"],
    ready: boolean,
  ) => React.ReactNode;
}) {
  const header = useHeaderStore((s) => s.header);
  return <>{children(header, isHeaderComplete(header))}</>;
}
