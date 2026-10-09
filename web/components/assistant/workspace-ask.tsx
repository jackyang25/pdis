"use client";

import { useMemo } from "react";
import { usePathname } from "next/navigation";
import { Ask } from "./ask";
import {
  isInspectorResultFinal,
  isScoutResultFinal,
  splitResultContext,
} from "@/lib/result-file";
import {
  useAlignerSession,
  useChunkerSession,
  useScreenerSession,
  useInspectorSession,
  useSearcherSession,
  useScoutSession,
} from "@/lib/session";
import { WORKSPACE_TOOLS } from "@/lib/tools";
import type { ContentBlock, PriorityReading } from "@/lib/api";
import { usePriorityReadingStore } from "@/lib/priority-reading";
import { reviewContextForAssistant, useAssistantReviewContext } from "@/lib/assistant-review-context";
import { resolveDocumentVersions } from "@/lib/workspace-documents";

type WorkspaceResult = {
  id: string;
  // Every tool that produces a result the assistant can read. A tool absent here has
  // a legend nothing ever reaches: Screener shipped with `SCREENER_LEGEND` registered and
  // no session collected, so Ask could interpret a gate review it was never handed.
  result_type:
    | "inspector"
    | "aligner"
    | "screener"
    | "scout"
    | "chunker"
    | "searcher";
  label: string;
  analysis: unknown;
  document_block_ids: string[];
  /**
   * The priority card's reading of this run, once it has been read.
   *
   * Not part of the analysis, because it is not part of the result: it is read when the
   * result is opened. It travels here so the assistant and the screen cannot disagree about
   * what a reader is looking at. Its points name findings by the IDs `analysis` carries.
   */
  priorities?: PriorityReading;
};

/**
 * One read-only assistant over the current client-held workspace. Tool stores
 * remain the source of truth; this component only builds a navigable bundle.
 */
export function WorkspaceAsk() {
  const pathname = usePathname();
  const chunker = useChunkerSession((state) => state.results);
  const inspector = useInspectorSession((state) => state.results);
  const aligner = useAlignerSession((state) => state.results);
  const screener = useScreenerSession((state) => state.results);
  const scout = useScoutSession((state) => state.results);
  const searcher = useSearcherSession((state) => state.results);
  const activeReview = useAssistantReviewContext(state => state.active);

  // Subscribed rather than read once: a reading lands after the result does, and the
  // bundle has to pick it up when it arrives.
  const readings = usePriorityReadingStore((state) => state.entries);
  const bundle = useMemo(() => {
    const results: WorkspaceResult[] = [];
    const blocks = new Map<string, ContentBlock>();

    function runLabel(name: string, createdAt: string): string {
      const day = new Date(createdAt);
      return Number.isNaN(day.getTime())
        ? name
        : `${name} · ${day.toLocaleDateString(undefined, { month: "short", day: "numeric" })}`;
    }

    // Collected rather than resolved immediately: a same-named document can arrive from
    // more than one run, and only once every run's blocks are in hand can
    // `resolveDocumentVersions` tell whether two runs read the same text or different
    // versions of it. A run's priority reading rides beside it: its points name findings,
    // never blocks, so resolving versions leaves it as it is. Inspector's readings live on
    // each review instead, so its run-level reading stays unset.
    const pending: {
      id: string;
      resultType: WorkspaceResult["result_type"];
      label: string;
      blocks: ContentBlock[];
      analysis: unknown;
      priorities?: PriorityReading;
    }[] = [];

    function readingFor(key: string): PriorityReading | undefined {
      const entry = readings[key];
      return entry?.state === "ready" ? entry.reading : undefined;
    }

    function addResult(
      id: string,
      resultType: WorkspaceResult["result_type"],
      label: string,
      value: unknown,
      priorities?: PriorityReading,
    ) {
      const context = splitResultContext(value);
      pending.push({
        id, resultType, label,
        blocks: context.document ?? [], analysis: context.analysis, priorities,
      });
    }

    for (const entry of inspector) {
      if (!isInspectorResultFinal(entry.result)) continue;
      addResult(
        entry.id,
        "inspector",
        runLabel(entry.result.inspection.doc_id || "Inspector result", entry.created_at),
        {
          ...entry.result.inspection,
          // All reviews travel together. A reading belongs to its own rubric; one from
          // the selected review must never speak for the run.
          reviews: entry.result.inspection.reviews.map(review => ({
            ...review,
            priorities: readingFor(`${entry.id}:${review.rubric.id}`),
          })),
        },
      );
    }

    for (const entry of chunker) {
      addResult(
        entry.id,
        "chunker",
        runLabel(entry.result.doc_id || "Parsed document", entry.created_at),
        entry.result,
      );
    }

    for (const entry of aligner) {
      const aligner = entry.result;
      // Named by the documents rather than by the comparisons: a run holds any
      // number of either, and the documents are what the user recognises.
      const names = aligner.alignment.documents
        .map((document) => document.doc_id)
        .filter(Boolean);
      addResult(
        entry.id,
        "aligner",
        runLabel(names.join(" · ") || "Documents", entry.created_at),
        aligner.alignment,
        readingFor(entry.id),
      );
    }

    for (const entry of screener) {
      const screener = entry.result;
      // Named by the gate, because the same documents are triaged again at every one
      // and the gate is what distinguishes two reviews of the same set.
      addResult(
        entry.id,
        "screener",
        runLabel(screener.review.gate_label || "Gate review", entry.created_at),
        screener.review,
        readingFor(entry.id),
      );
    }

    for (const entry of scout) {
      const scout = entry.result;
      if (!isScoutResultFinal(scout)) continue;
      const documentIds = Array.from(
        new Set(scout.blocks.map((block) => block.doc_id).filter(Boolean)),
      );
      addResult(
        entry.id,
        "scout",
        runLabel(documentIds[0] || scout.indication || "Scout result", entry.created_at),
        scout,
        readingFor(entry.id),
      );
    }

    for (const entry of searcher) {
      addResult(
        entry.id,
        "searcher",
        runLabel("Evidence search", entry.created_at),
        entry.result,
      );
    }

    // Decided once every run is collected: two runs holding the same document name are
    // one document only if their blocks actually agree, and only `resolveDocumentVersions`
    // can tell — a run added to `results` and `blocks` before this point would have its
    // citations resolved against whichever version happened to be inserted first.
    for (const run of resolveDocumentVersions(pending)) {
      const documentBlockIds = run.blocks.map((block) => block.id);
      for (const block of run.blocks) {
        if (!blocks.has(block.id)) blocks.set(block.id, block);
      }
      results.push({
        id: run.id,
        result_type: run.resultType,
        label: run.label,
        analysis: run.analysis,
        document_block_ids: documentBlockIds,
        priorities: run.priorities,
      });
    }

    // Review drafts remain outside results: they cannot satisfy final-result skills
    // or change export. Reuse the same navigable tree and source readers.
    const reviewContext = activeReview ? reviewContextForAssistant(activeReview) : null;
    for (const block of reviewContext?.document ?? []) blocks.set(block.id, block);
    const active_review = activeReview && reviewContext ? {
      result_type: "scout",
      phase: activeReview.draft.phase,
      selected_item: activeReview.selection,
      analysis: reviewContext.analysis,
      document_block_ids: (reviewContext.document ?? []).map(block => block.id),
    } : undefined;

    const catalog = WORKSPACE_TOOLS.map((tool) => ({
      id: tool.id,
      title: tool.title,
      description: tool.description,
      audience: tool.audience,
      workflow: tool.workflow,
      availability: tool.availability,
    }));

    return {
      result: {
        catalog,
        results,
        active_review,
        blocks: Array.from(blocks.values()),
      },
      resultCount: results.length,
    };
  }, [aligner, chunker, readings, screener, inspector, scout, searcher, activeReview]);

  return (
    <Ask
      result={bundle.result}
      availableResultCount={bundle.resultCount}
      reviewPhase={activeReview?.draft.phase}
      display={pathname === "/ask" ? "page" : "floating"}
    />
  );
}
