"use client";

import { useHeaderStore, isHeaderComplete } from "@/lib/store";
import { EmptyState } from "./empty-state";

export function HeaderGuard({ children }: { children: (header: ReturnType<typeof useHeaderStore.getState>["header"]) => React.ReactNode }) {
  const header = useHeaderStore((s) => s.header);
  if (!isHeaderComplete(header)) {
    return (
      <EmptyState message="Pick org, source type, and intervention in the sidebar to begin." />
    );
  }
  return <>{children(header)}</>;
}
