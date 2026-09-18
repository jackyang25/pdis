"use client";

import { QUEUED_STAGE } from "@/lib/api";
import {
  useAlignerSession, useChunkerSession, useInspectorSession,
  useScoutSession, useScreenerSession, useSearcherSession,
} from "@/lib/session";

export type ToolStatus = "Waiting for capacity" | "Running" | "Ready for review" | "Results available";

type SessionStatusInput = {
  busy: boolean;
  stage: string | null;
  results: readonly unknown[];
};

/** Workflow facts only, not an assessment of result quality or deployment state. */
export function toolStatus(session: SessionStatusInput, needsReview = false): ToolStatus | null {
  if (session.busy) return session.stage === QUEUED_STAGE ? "Waiting for capacity" : "Running";
  if (needsReview) return "Ready for review";
  return session.results.length > 0 ? "Results available" : null;
}

/** Select primitive values so progress ticks do not rerender the tool catalog. */
export function useToolStatuses(): Record<string, ToolStatus | null> {
  return {
    inspector: useInspectorSession(toolStatus),
    aligner: useAlignerSession(toolStatus),
    screener: useScreenerSession(toolStatus),
    scout: useScoutSession(session => toolStatus(session,
      session.result?.phase === "target_review" || session.result?.phase === "evidence_review")),
    chunker: useChunkerSession(toolStatus),
    searcher: useSearcherSession(toolStatus),
  };
}
