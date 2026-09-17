"use client";

import { useEffect, useId } from "react";
import { create } from "zustand";
import type { ScoutResponse } from "./api";
import { splitResultContext } from "./result-file.ts";

export type ReviewSelection =
  | { kind: "target"; target_id: string }
  | { kind: "statement"; unit_id: string }
  | { kind: "evidence"; target_id: string; candidate_ids: string[]; selected_candidate_id: string | null };

type ActiveReview = { owner: string; draft: ScoutResponse; selection: ReviewSelection | null };

/** Transport-only aliases keep a revised upload distinct from same-name final sources.
 * Canonical IDs survive in metadata; neither the stored draft nor exports are changed.
 */
export function reviewContextForAssistant(context: ActiveReview) {
  const { analysis, document } = splitResultContext(context.draft);
  const aliases = new Map((document ?? []).map(block => [block.id, `review:${context.owner}/${block.id}`]));
  const referenceFields = new Set(["block_id", "block_ids", "doc_block_ids"]);
  function rewrite(value: unknown, field = ""): unknown {
    if (typeof value === "string") return referenceFields.has(field) ? aliases.get(value) ?? value : value;
    if (Array.isArray(value)) return value.map(item => rewrite(item, field));
    if (value && typeof value === "object") return Object.fromEntries(Object.entries(value).map(([key, child]) => [key, rewrite(child, key)]));
    return value;
  }
  return {
    analysis: rewrite(analysis),
    document: (document ?? []).map(block => ({
      ...block, id: aliases.get(block.id)!, doc_id: `Review draft · ${block.doc_id}`,
      structural_meta: { ...block.structural_meta, source_block_id: block.id, source_doc_id: block.doc_id },
    })),
  };
}

/** A reference to the mounted panel, never a second draft or persisted result. */
export const useAssistantReviewContext = create<{
  active: ActiveReview | null;
  publish: (context: ActiveReview) => void;
  clear: (owner: string) => void;
}>(set => ({
  active: null,
  publish: context => set({ active: context.draft.phase === "target_review" || context.draft.phase === "evidence_review" ? context : null }),
  clear: owner => set(state => state.active?.owner === owner ? { active: null } : state),
}));

/** Removing/changing the checkpoint removes/replaces its read-only chat context. */
export function usePublishReviewContext(draft: ScoutResponse, selection: ReviewSelection | null) {
  const owner = useId();
  useEffect(() => {
    useAssistantReviewContext.getState().publish({ owner, draft, selection });
    return () => useAssistantReviewContext.getState().clear(owner);
  }, [owner, draft, selection]);
}
