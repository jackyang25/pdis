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
  useExpertSession,
  useInspectorSession,
  useSearcherSession,
  useScoutSession,
} from "@/lib/session";
import { EXTERNAL_TOOLS, WORKSPACE_TOOLS } from "@/lib/tools";
import type { ContentBlock } from "@/lib/api";

type WorkspaceResult = {
  id: string;
  // Every tool that produces a result the assistant can read. A tool absent here has
  // a legend nothing ever reaches: Expert shipped with `EXPERT_LEGEND` registered and
  // no session collected, so Ask could interpret a gate review it was never handed.
  result_type:
    | "inspector"
    | "aligner"
    | "expert"
    | "scout"
    | "chunker"
    | "searcher";
  label: string;
  analysis: unknown;
  document_block_ids: string[];
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
  const expert = useExpertSession((state) => state.results);
  const scout = useScoutSession((state) => state.results);
  const searcher = useSearcherSession((state) => state.results);

  const bundle = useMemo(() => {
    const results: WorkspaceResult[] = [];
    const blocks = new Map<string, ContentBlock>();

    function runLabel(name: string, createdAt: string): string {
      const day = new Date(createdAt);
      return Number.isNaN(day.getTime())
        ? name
        : `${name} · ${day.toLocaleDateString(undefined, { month: "short", day: "numeric" })}`;
    }

    function addResult(
      id: string,
      resultType: WorkspaceResult["result_type"],
      label: string,
      value: unknown,
    ) {
      const context = splitResultContext(value);
      const documentBlockIds: string[] = [];
      for (const block of context.document ?? []) {
        documentBlockIds.push(block.id);
        if (!blocks.has(block.id)) blocks.set(block.id, block);
      }
      results.push({
        id,
        result_type: resultType,
        label,
        analysis: context.analysis,
        document_block_ids: documentBlockIds,
      });
    }

    for (const entry of inspector) {
      if (!isInspectorResultFinal(entry.result)) continue;
      addResult(
        entry.id,
        "inspector",
        runLabel(entry.result.inspection.doc_id || "Inspector result", entry.created_at),
        entry.result.inspection,
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
      );
    }

    for (const entry of expert) {
      const expert = entry.result;
      // Named by the gate, because the same documents are triaged again at every one
      // and the gate is what distinguishes two reviews of the same set.
      addResult(
        entry.id,
        "expert",
        runLabel(expert.review.gate_label || "Gate review", entry.created_at),
        expert.review,
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

    const catalog = [...WORKSPACE_TOOLS, ...EXTERNAL_TOOLS].map((tool) => ({
      id: tool.id,
      title: tool.title,
      description: tool.description,
      capability: tool.capability,
      audience: tool.audience,
      workflow: tool.workflow,
      availability: tool.availability,
      delivery: tool.delivery,
      providers: tool.delivery === "external"
        ? tool.shortcuts.map((shortcut) => shortcut.label)
        : [],
    }));

    return {
      result: {
        catalog,
        results,
        blocks: Array.from(blocks.values()),
      },
      resultCount: results.length,
    };
  }, [aligner, chunker, expert, inspector, scout, searcher]);

  return (
    <Ask
      resultType="workspace"
      result={bundle.result}
      availableResultCount={bundle.resultCount}
      display={pathname === "/ask" ? "page" : "floating"}
    />
  );
}
