"use client";

import { create } from "zustand";
import type {
  ContentBlock,
  Claim,
  MonitorResponse,
  ReviewerResponse,
  SearcherResponse,
} from "./api";

type ToolSession<TResult> = {
  result: TResult | null;
  busy: boolean;
  stage: string | null;
  error: string | null;
  setResult: (r: TResult | null) => void;
  setBusy: (b: boolean) => void;
  setStage: (s: string | null) => void;
  setError: (e: string | null) => void;
  reset: () => void;
};

function createToolSession<TResult>() {
  return create<ToolSession<TResult>>((set) => ({
    result: null,
    busy: false,
    stage: null,
    error: null,
    setResult: (result) => set({ result }),
    setBusy: (busy) => set({ busy }),
    setStage: (stage) => set({ stage }),
    setError: (error) => set({ error }),
    reset: () => set({ result: null, busy: false, stage: null, error: null }),
  }));
}

export type ChunkerResult = { doc_id: string; blocks: ContentBlock[] };
export type BenchmarkerResult = { doc_id: string; source_id: string; claims: Claim[] };
export type ReviewerResult = ReviewerResponse;
export type SearcherResult = SearcherResponse;
export type MonitorResult = MonitorResponse;

export const useChunkerSession = createToolSession<ChunkerResult>();
export const useBenchmarkerSession = createToolSession<BenchmarkerResult>();
export const useReviewerSession = createToolSession<ReviewerResult>();
export const useSearcherSession = createToolSession<SearcherResult>();
export const useMonitorSession = createToolSession<MonitorResult>();
