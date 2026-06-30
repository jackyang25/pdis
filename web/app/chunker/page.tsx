"use client";

import { PageHeader } from "@/components/page-header";
import { RunPanel } from "@/components/run-panel";
import { HeaderGuard } from "@/components/header-guard";
import { EmptyState } from "@/components/empty-state";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { DownloadButton } from "@/components/download-button";
import { CollapsibleCard } from "@/components/collapsible-card";
import { runChunker, type ContentBlock, type Header } from "@/lib/api";
import { useChunkerSession } from "@/lib/session";

const CHUNKER_STEPS = [
  { key: "parse", label: "Parsing document" },
  { key: "describe", label: "Describing figures" },
  { key: "label", label: "Labeling sections" },
];

export default function ChunkerPage() {
  return (
    <>
      <PageHeader
        title="Chunker"
        description="Parse a document into ordered content blocks with optional section labels."
      />
      <HeaderGuard>
        {(header, ready) => <ChunkerView header={header as Header} ready={ready} />}
      </HeaderGuard>
    </>
  );
}

function ChunkerView({ header, ready }: { header: Header; ready: boolean }) {
  const { result, busy, stage, error, setResult, setBusy, setStage, setError } =
    useChunkerSession();

  async function handleRun(file: File) {
    setBusy(true);
    setError(null);
    setStage(null);
    try {
      const res = await runChunker(file, header, setStage);
      setResult(res);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const blocks = result?.blocks ?? null;

  return (
    <div className="flex flex-col gap-6">
      <RunPanel
        accept=".docx,.pdf"
        busy={busy}
        onRun={handleRun}
        steps={CHUNKER_STEPS}
        currentStage={stage}
        runDisabled={!ready}
        hint={ready ? undefined : "Select org, source type & intervention in the sidebar to run."}
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
  const labeledCount = blocks.filter((b) => b.section_label).length;
  return (
    <CollapsibleCard
      title={`${blocks.length} blocks`}
      subtitle={`${labeledCount} labeled`}
      trailing={
        <DownloadButton
          filename={`${docId}_blocks.jsonl`}
          data={blocks}
          format="jsonl"
          label="Download JSONL"
        />
      }
    >
      <ul className="-mx-6 divide-y divide-border">
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
    </CollapsibleCard>
  );
}
