"use client";

import { useEffect } from "react";
import { create } from "zustand";

import { fetchPriorityReading, type PriorityReading } from "./api";
import { priorityRequest, type PriorityLens } from "./priorities.ts";

/**
 * One reading per result, held for the session and nowhere else.
 *
 * Derived, never stored in a result: it is read when a result is opened, so it improves with
 * the prompt, and every saved file keeps working without a migration.
 *
 * Kept in a store rather than component state for one reason: Ask must be able to see it.
 * The card is on screen and not in the result, so an assistant without it would answer
 * questions about the card while missing what a reader is looking at.
 *
 * Keyed by result id, so switching tabs or tools does not re-read, and re-opening a result
 * is free. One request per result per session, unless a reader retries a failure.
 */

type Entry =
  | { state: "loading" }
  | { state: "ready"; reading: PriorityReading }
  | { state: "failed"; reason: string };

type ReadingStore = {
  entries: Record<string, Entry>;
  read: (key: string, request: () => Promise<PriorityReading>) => void;
  /**
   * Clears a failed read so the next render reads again.
   *
   * Only a failure: a reading that arrived describes a result that has not changed, and one
   * in flight is already the retry.
   */
  retry: (key: string) => void;
};

export const usePriorityReadingStore = create<ReadingStore>((set, get) => ({
  entries: {},
  read: (key, request) => {
    if (get().entries[key]) return;
    set((current) => ({ entries: { ...current.entries, [key]: { state: "loading" } } }));
    void request()
      .then((reading) =>
        set((current) => ({
          entries: { ...current.entries, [key]: { state: "ready", reading } },
        })),
      )
      // The reason is kept: a skeleton followed by nothing is indistinguishable from a tool
      // that has no card. It is still not a banner — the result below is complete without a
      // reading, so a failure is reported quietly where the reading would have been.
      .catch((error: Error) =>
        set((current) => ({
          entries: { ...current.entries, [key]: { state: "failed", reason: error.message } },
        })),
      );
  },
  retry: (key) => {
    if (get().entries[key]?.state !== "failed") return;
    set((current) => {
      const { [key]: _failed, ...entries } = current.entries;
      return { entries };
    });
  },
}));

/**
 * What a page reads: the stored entry, and on a failure the way to ask again.
 *
 * Not retried on its own — each read is a model call, and a failure that is not transient
 * would repeat on every render — but the reader who sees it can ask again.
 */
export type ReadingView =
  | { state: "loading" }
  | { state: "ready"; reading: PriorityReading }
  | { state: "failed"; reason: string; retry: () => void };

/**
 * Reads one result's card, once — again only when a reader retries a failure.
 *
 * Skipped when the result holds no findings: there is nothing to read.
 */
export function usePriorityReading(
  resultId: string | null,
  lens: PriorityLens,
): ReadingView | undefined {
  const read = usePriorityReadingStore((state) => state.read);
  const retry = usePriorityReadingStore((state) => state.retry);
  const entry = usePriorityReadingStore((state) =>
    resultId ? state.entries[resultId] : undefined,
  );

  const held = entry !== undefined;
  const empty = lens.findings.length === 0;
  useEffect(() => {
    if (!resultId || empty || held) return;
    read(resultId, () => fetchPriorityReading(priorityRequest(lens)));
    // Keyed on the result alone. The lens is derived from it, so a new object identity on
    // every render must not start a second request. `held` is here so that clearing a
    // failure reads again.
  }, [empty, held, resultId, read]);

  if (!entry || !resultId) return undefined;
  return entry.state === "failed" ? { ...entry, retry: () => retry(resultId) } : entry;
}
