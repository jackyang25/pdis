"use client";

import { useEffect } from "react";
import { create } from "zustand";

import { fetchPriorityDigest, type PriorityDigest } from "./api";
import type { PriorityItem } from "@/components/ui/priority-panel";

/**
 * One read over a tool's selected priorities, held for the session and nowhere else.
 *
 * Derived, never stored in a result. The digest describes the priority list, and that list
 * is itself computed when a result is opened — change what qualifies as a priority and the
 * same saved result shows a different list. A digest frozen into the result would be a
 * paragraph describing a list that had moved under it, sitting directly above it.
 *
 * Kept in a store rather than component state for one reason: Ask must be able to see it.
 * The nominations are findings the screen shows and the result does not contain, so an
 * assistant without them would answer questions about this panel while missing part of
 * what a reader is looking at — the same disagreement the trace and the chat had.
 *
 * Keyed by result id, so switching tabs or tools does not re-read, and re-opening a result
 * is free. One request per result per session.
 */

type Entry =
  | { state: "loading" }
  | { state: "ready"; digest: PriorityDigest }
  | { state: "failed" };

type DigestStore = {
  entries: Record<string, Entry>;
  /**
   * Which items the tool's selector chose, in its order, per result.
   *
   * Recorded separately from the digest because it is a different fact and outlives a
   * failed read: the panel selected these whether or not a digest was ever produced.
   * IDs only — every label and statement is already in the analysis the assistant
   * receives, so sending them again would be one finding described twice.
   */
  selected: Record<string, string[]>;
  read: (key: string, request: () => Promise<PriorityDigest>) => void;
  /** Records the selection, when it changes. */
  select: (key: string, itemIds: string[]) => void;
};

export const usePriorityDigestStore = create<DigestStore>((set, get) => ({
  entries: {},
  selected: {},
  select: (key, itemIds) => {
    const held = get().selected[key];
    if (held && held.length === itemIds.length && held.every((id, at) => id === itemIds[at])) {
      return;
    }
    set((current) => ({ selected: { ...current.selected, [key]: itemIds } }));
  },
  read: (key, request) => {
    if (get().entries[key]) return;
    set((current) => ({ entries: { ...current.entries, [key]: { state: "loading" } } }));
    void request()
      .then((digest) =>
        set((current) => ({
          entries: { ...current.entries, [key]: { state: "ready", digest } },
        })),
      )
      // Silent: the panel is complete without it. A failure banner over a working list
      // would report the absence of an addition as a fault in the result.
      .catch(() =>
        set((current) => ({ entries: { ...current.entries, [key]: { state: "failed" } } })),
      );
  },
}));

/** What a tool hands over. Everything that differs between tools is already published. */
export type DigestSubject = {
  /** Stable per result, so two results of one tool are read separately. */
  resultId: string;
  /** The tool's catalog sentence: what it reads, and the authority it judges against. */
  authority: string;
  /** How the deterministic list was ordered, in the tool's own words. */
  orderNote: string;
  items: PriorityItem[];
  /** The result's analysis without its blocks. */
  analysis: unknown;
  blockIds: string[];
  org: string;
  interventionClass: string;
  indication: string;
};

/**
 * Reads the digest for one result, once.
 *
 * Skipped entirely when the tool selected nothing: there is no list to describe, and the
 * panel's empty message is already the whole answer.
 */
export function usePriorityDigest(subject: DigestSubject | null): Entry | undefined {
  const read = usePriorityDigestStore((state) => state.read);
  const select = usePriorityDigestStore((state) => state.select);
  const entry = usePriorityDigestStore((state) =>
    subject ? state.entries[subject.resultId] : undefined,
  );

  const key = subject?.resultId;
  const empty = (subject?.items.length ?? 0) === 0;
  const itemIds = (subject?.items ?? []).map((item) => item.id).join("\u0000");
  useEffect(() => {
    if (!key) return;
    select(key, itemIds ? itemIds.split("\u0000") : []);
    // Keyed on the joined IDs rather than the array, whose identity changes every render.
  }, [itemIds, key, select]);
  useEffect(() => {
    if (!subject || !key || empty) return;
    read(key, () =>
      fetchPriorityDigest({
        authority: subject.authority,
        order_note: subject.orderNote,
        items: subject.items.map((item) => ({
          id: item.id,
          label: item.label,
          qualifier: item.qualifier ?? "",
          statement: item.statement,
          recommendation: item.recommendation ?? "",
        })),
        analysis: subject.analysis,
        block_ids: subject.blockIds,
        org: subject.org,
        intervention_class: subject.interventionClass,
        indication: subject.indication,
      }),
    );
    // Deliberately keyed on the result alone. The items are derived from it, so a new
    // array identity on every render must not start a second request.
  }, [empty, key, read]);

  return entry;
}


