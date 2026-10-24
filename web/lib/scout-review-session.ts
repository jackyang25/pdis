import type { ScoutResponse } from "./api";
import { pendingQuantitativeReviewCount } from "./result-contracts.ts";

export type ScoutReviewStatus = "targets" | "reviewing" | "ready" | "final";

/**
 * Where one run stands in Scout's review, read from that run alone.
 *
 * Derived rather than held: a single status kept for the whole tool outlived the run
 * it described, so selecting another run from history rendered whichever checkpoint
 * the previous one had reached, or nothing. Everything the status says is already on
 * the result - its phase, and how many candidates still need a decision - so the
 * result is the only authority. `ready` is still not `final`: finalizing is the
 * reviewer's explicit act, recorded by setting the phase.
 */
export function scoutReviewStatus(result: ScoutResponse): ScoutReviewStatus {
  if (result.phase === "target_review") return "targets";
  if (result.phase === "final") return "final";
  return pendingQuantitativeReviewCount(result) > 0 ? "reviewing" : "ready";
}
