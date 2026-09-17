"use client";

import { create } from "zustand";

export type ScoutReviewStatus = "idle" | "reviewing" | "ready" | "final";

type ScoutReviewSession = {
  status: ScoutReviewStatus;
  initialize: (hasPendingReview: boolean) => void;
  recordDecision: (hasPendingReview: boolean) => void;
  finalize: () => void;
  reset: () => void;
};

/**
 * Client-held workflow state only. The analysis remains in useScoutSession;
 * this store records whether that analysis is a draft, ready to finalize, or
 * locked for presentation/export. No hidden server state is introduced.
 */
export const useScoutReviewSession = create<ScoutReviewSession>((set) => ({
  status: "idle",
  initialize: (hasPendingReview) => set({
    status: hasPendingReview ? "reviewing" : "final",
  }),
  recordDecision: (hasPendingReview) => set({
    status: hasPendingReview ? "reviewing" : "ready",
  }),
  finalize: () => set({ status: "final" }),
  reset: () => set({ status: "idle" }),
}));
