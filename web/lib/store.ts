import { create } from "zustand";
import type { Header } from "./api";

type HeaderState = {
  header: Partial<Header>;
  setHeader: (next: Partial<Header>) => void;
  reset: () => void;
};

export const useHeaderStore = create<HeaderState>((set) => ({
  header: {},
  setHeader: (next) => set((state) => ({ header: { ...state.header, ...next } })),
  reset: () => set({ header: {} }),
}));

/**
 * The context every tool needs: org, intervention, indication.
 *
 * Separate from `isHeaderComplete` because a tool that reads several documents
 * has several source types and holds them itself, so it can be ready to run
 * without one in the store.
 */
export function isContextComplete(
  h: Partial<Header>,
): h is Omit<Header, "source_type"> & Partial<Header> {
  return Boolean(h.org && h.intervention_class && h.indication);
}

/** The context plus the one document type a single-document tool reads. */
export function isHeaderComplete(h: Partial<Header>): h is Header {
  return isContextComplete(h) && Boolean(h.source_type);
}

