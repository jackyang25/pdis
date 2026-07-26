"use client";

import { create } from "zustand";
import type { Conformity } from "./api";
import type { QuantitativeReviewDecision } from "./quantitative-review";

export type ScoutReviewStatus = "idle" | "reviewing" | "ready" | "final";

export type ScoutReviewHistoryEntry = {
  decision: QuantitativeReviewDecision | "bulk";
  previousConformity: Conformity[];
};

type ScoutReviewSession = {
  status: ScoutReviewStatus;
  history: ScoutReviewHistoryEntry[];
  initialize: (hasPendingReview: boolean) => void;
  recordDecision: (entry: ScoutReviewHistoryEntry, hasPendingReview: boolean) => void;
  undoLast: () => ScoutReviewHistoryEntry | null;
  finalize: () => void;
  reset: () => void;
};

/**
 * Client-held workflow state only. The analysis remains in useScoutSession;
 * this store records whether that analysis is a draft, ready to finalize, or
 * locked for presentation/export. No hidden server state is introduced.
 */
export const useScoutReviewSession = create<ScoutReviewSession>((set, get) => ({
  status: "idle",
  history: [],
  initialize: (hasPendingReview) => set({
    status: hasPendingReview ? "reviewing" : "final",
    history: [],
  }),
  recordDecision: (entry, hasPendingReview) => set((state) => ({
    status: hasPendingReview ? "reviewing" : "ready",
    history: [...state.history, entry],
  })),
  undoLast: () => {
    const history = get().history;
    const entry = history.at(-1) ?? null;
    if (!entry) return null;
    set({ status: "reviewing", history: history.slice(0, -1) });
    return entry;
  },
  finalize: () => set({ status: "final", history: [] }),
  reset: () => set({ status: "idle", history: [] }),
}));
