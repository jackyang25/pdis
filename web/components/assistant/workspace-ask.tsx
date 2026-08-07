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
  const chunker = useChunkerSession((state) => state.result);
  const inspector = useInspectorSession((state) => state.result);
  const aligner = useAlignerSession((state) => state.result);
  const expert = useExpertSession((state) => state.result);
  const scout = useScoutSession((state) => state.result);
  const searcher = useSearcherSession((state) => state.result);

  const bundle = useMemo(() => {
    const results: WorkspaceResult[] = [];
    const blocks = new Map<string, ContentBlock>();

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

    if (inspector && isInspectorResultFinal(inspector)) {
      addResult(
        "inspector-current",
        "inspector",
        inspector.inspection.doc_id || "Inspector result",
        inspector.inspection,
      );
    }

    if (chunker) {
      addResult(
        "chunker-current",
        "chunker",
        chunker.doc_id || "Parsed document",
        chunker,
      );
    }

    if (aligner) {
      // Named by the documents rather than by the comparisons: a run holds any
      // number of either, and the documents are what the user recognises.
      const names = aligner.alignment.documents
        .map((document) => document.doc_id)
        .filter(Boolean);
      addResult(
        "aligner-current",
        "aligner",
        names.join(" · ") || "Documents",
        aligner.alignment,
      );
    }

    if (expert) {
      // Named by the gate, because the same documents are triaged again at every one
      // and the gate is what distinguishes two reviews of the same set.
      addResult(
        "expert-current",
        "expert",
        expert.review.gate_label || "Gate review",
        expert.review,
      );
    }

    if (scout && isScoutResultFinal(scout)) {
      const documentIds = Array.from(
        new Set(scout.blocks.map((block) => block.doc_id).filter(Boolean)),
      );
      addResult(
        "scout-current",
        "scout",
        documentIds[0] || scout.indication || "Scout result",
        scout,
      );
    }

    if (searcher) {
      addResult(
        "searcher-current",
        "searcher",
        "Current evidence search",
        searcher,
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
