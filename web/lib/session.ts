"use client";

import { create } from "zustand";
import type {
  ContentBlock,
  AlignerResponse,
  ExpertResponse,
  ScoutResponse,
  InspectorResponse,
  SearcherResponse,
  StageProgress,
} from "./api";

/**
 * How many finished runs one tool keeps for the session.
 *
 * Not a memory limit: nothing here is persisted, so a tab holding five results
 * is cheap. It bounds what Ask re-sends, because the assistant is stateless by
 * design and the client submits its whole bundle with every message. Five
 * results is five analyses per question asked.
 *
 * At the limit a run is refused rather than the oldest silently dropped: a user
 * who ran six things and found the first gone would read that as a fault. The
 * conversation attachment limit takes the same position.
 */
export const MAX_RESULTS_PER_TOOL = 5;

/**
 * What a reader is told when a run cannot be kept.
 *
 * Owned here rather than written at each call site. Two of six tools used to check the
 * limit before running and four did not, so a fifth run on those finished, cost its time,
 * and then silently failed to appear — the history simply did not grow. The refusal is now
 * the store's own, because the store is the only thing that knows it happened.
 */
export const RESULT_LIMIT_MESSAGE =
  `Keeping ${MAX_RESULTS_PER_TOOL} runs. Remove one before starting another.`;

/** The same refusal, for an import rather than a run. */
export const IMPORT_LIMIT_MESSAGE =
  `Keeping ${MAX_RESULTS_PER_TOOL} runs. Remove one before importing another.`;

export type StoredResult<TResult> = {
  /** Stable across export and re-import, so the same file is never held twice. */
  id: string;
  /** ISO instant the run finished, or the moment a file was imported. */
  created_at: string;
  result: TResult;
};

export type AddResultOutcome =
  | { added: true; id: string }
  | { added: false; reason: "at_limit" | "duplicate"; id: string };

type ToolSession<TResult> = {
  /** Finished runs, newest first. */
  results: StoredResult<TResult>[];
  selectedId: string | null;
  /**
   * The run being viewed. Derived from `results` and `selectedId` and kept in
   * step with them, so every existing reader — the tool pages, the download
   * button, the Ask bundle — is unchanged by history existing.
   */
  result: TResult | null;
  busy: boolean;
  stage: string | null;
  progress: StageProgress | null;
  error: string | null;
  /**
   * Record a finished run or an import. Mints identity when the caller has
   * none, which is the case for a run; an imported file brings its own.
   */
  addResult: (
    result: TResult,
    identity?: { id?: string; created_at?: string },
  ) => AddResultOutcome;
  /**
   * Replace what the selected run holds, in place.
   *
   * Review is a sequence of edits to one run — approving a target, finalizing a
   * phase — so these must not each become a new entry in the history.
   */
  setResult: (r: TResult | null) => void;
  selectResult: (id: string) => void;
  removeResult: (id: string) => void;
  setBusy: (b: boolean) => void;
  setStage: (s: string | null) => void;
  setProgress: (p: StageProgress | null) => void;
  setError: (e: string | null) => void;
  reset: () => void;
};

function newId(): string {
  return globalThis.crypto?.randomUUID?.() ?? `run-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

function createToolSession<TResult>() {
  return create<ToolSession<TResult>>((set, get) => ({
    results: [],
    selectedId: null,
    result: null,
    busy: false,
    stage: null,
    progress: null,
    error: null,

    addResult: (result, identity) => {
      const { results } = get();
      const id = identity?.id ?? newId();
      const existing = results.find((entry) => entry.id === id);
      if (existing) {
        // Re-importing a file already held selects it rather than duplicating
        // it. A re-run is a different run and arrives with its own id.
        set({ selectedId: id, result: existing.result });
        return { added: false, reason: "duplicate", id };
      }
      if (results.length >= MAX_RESULTS_PER_TOOL) {
        // Reported here, not left to the caller. `AddResultOutcome` is a return value a
        // page can discard without TypeScript minding, and four of six did — so the one
        // place that can tell the result was dropped is the one that says so.
        set({ error: RESULT_LIMIT_MESSAGE });
        return { added: false, reason: "at_limit", id };
      }
      const entry: StoredResult<TResult> = {
        id,
        created_at: identity?.created_at ?? new Date().toISOString(),
        result,
      };
      set({ results: [entry, ...results], selectedId: id, result });
      return { added: true, id };
    },

    setResult: (result) => {
      const { results, selectedId } = get();
      if (result === null) {
        set({ selectedId: null, result: null });
        return;
      }
      if (selectedId === null) {
        get().addResult(result);
        return;
      }
      set({
        results: results.map((entry) =>
          entry.id === selectedId ? { ...entry, result } : entry,
        ),
        result,
      });
    },

    selectResult: (id) => {
      const entry = get().results.find((item) => item.id === id);
      if (entry) set({ selectedId: id, result: entry.result });
    },

    removeResult: (id) => {
      const remaining = get().results.filter((entry) => entry.id !== id);
      const stillSelected = remaining.some((entry) => entry.id === get().selectedId);
      const next = stillSelected
        ? remaining.find((entry) => entry.id === get().selectedId)
        : remaining[0];
      set({
        results: remaining,
        selectedId: next?.id ?? null,
        result: next?.result ?? null,
      });
    },

    setBusy: (busy) => set({ busy }),
    setStage: (stage) => set({ stage }),
    setProgress: (progress) => set({ progress }),
    setError: (error) => set({ error }),
    reset: () =>
      set({
        results: [],
        selectedId: null,
        result: null,
        busy: false,
        stage: null,
        progress: null,
        error: null,
      }),
  }));
}

export type ChunkerResult = { doc_id: string; blocks: ContentBlock[] };
export type InspectorResult = InspectorResponse;
export type SearcherResult = SearcherResponse;
export type ScoutResult = ScoutResponse;
export type AlignerResult = AlignerResponse;
export type ExpertResult = ExpertResponse;

export const useChunkerSession = createToolSession<ChunkerResult>();
export const useInspectorSession = createToolSession<InspectorResult>();
export const useSearcherSession = createToolSession<SearcherResult>();
export const useScoutSession = createToolSession<ScoutResult>();
export const useAlignerSession = createToolSession<AlignerResult>();
export const useExpertSession = createToolSession<ExpertResult>();
