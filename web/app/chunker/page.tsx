"use client";

import { useState } from "react";
import { PageHeader } from "@/components/page-header";
import { RunPanel } from "@/components/run-panel";
import { HeaderGuard } from "@/components/header-guard";
import { EmptyState } from "@/components/empty-state";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { DownloadButton } from "@/components/download-button";
import { runChunker, type ContentBlock, type Header } from "@/lib/api";

export default function ChunkerPage() {
  return (
    <>
      <PageHeader
        title="Chunker"
        description="Parse a document into ordered content blocks with optional section labels."
      />
      <HeaderGuard>{(header) => <ChunkerView header={header as Header} />}</HeaderGuard>
    </>
  );
}

function ChunkerView({ header }: { header: Header }) {
  const [blocks, setBlocks] = useState<ContentBlock[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleRun(file: File) {
    setBusy(true);
    setError(null);
    try {
      const res = await runChunker(file, header, { label: true });
      setBlocks(res.blocks);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <RunPanel
        accept=".docx,.pdf"
        busy={busy}
        onRun={handleRun}
        steps={["Parse document", "Label sections"]}
      />
      {error && <p className="text-sm text-destructive">{error}</p>}
      {blocks && <BlocksList blocks={blocks} />}
      {!blocks && !busy && !error && (
        <EmptyState message="Upload a .docx or .pdf to begin." />
      )}
    </div>
  );
}

function BlocksList({ blocks }: { blocks: ContentBlock[] }) {
  const docId = blocks[0]?.doc_id ?? "blocks";
  return (
    <div className="rounded-lg border border-border bg-card">
      <div className="flex items-center justify-between px-6 py-4">
        <h2 className="text-sm font-semibold">{blocks.length} blocks</h2>
        <DownloadButton
          filename={`${docId}_blocks.jsonl`}
          data={blocks}
          format="jsonl"
          label="Download JSONL"
        />
      </div>
      <Separator />
      <ul className="divide-y divide-border">
        {blocks.map((block) => (
          <li key={block.id} className="px-6 py-4">
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Badge variant="outline">{block.block_type}</Badge>
              {block.section_label && <Badge variant="muted">{block.section_label}</Badge>}
              <span className="font-mono">{block.id}</span>
            </div>
            {block.heading_stack.length > 0 && (
              <div className="mt-2 text-xs text-muted-foreground">
                {block.heading_stack.join(" › ")}
              </div>
            )}
            <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed">{block.content}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}
