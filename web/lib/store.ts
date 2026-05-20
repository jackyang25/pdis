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

export function isHeaderComplete(h: Partial<Header>): h is Header {
  return Boolean(
    h.org && h.source_type && h.intervention_class && h.indication,
  );
}

