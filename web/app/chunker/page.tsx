"use client";

import { useRef } from "react";
import { ChevronDown } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { RunPanel } from "@/components/run-panel";
import { HeaderGuard } from "@/components/header-guard";
import { EmptyState } from "@/components/empty-state";
import { Badge } from "@/components/ui/badge";
import { DownloadButton } from "@/components/download-button";
import { CollapsibleCard } from "@/components/collapsible-card";
import { runChunker, type ContentBlock, type Header } from "@/lib/api";
import { useChunkerSession, type ChunkerResult } from "@/lib/session";

const CHUNKER_STEPS = [
  { key: "parse", label: "Parsing document" },
  { key: "describe", label: "Describing figures" },
  { key: "label", label: "Labeling sections" },
];

export default function ChunkerPage() {
  return (
    <>
      <PageHeader title="Chunker" />
      <HeaderGuard>
        {(header, ready) => <ChunkerView header={header as Header} ready={ready} />}
      </HeaderGuard>
    </>
  );
}

function ChunkerView({ header, ready }: { header: Header; ready: boolean }) {
  const { result, busy, stage, error, setResult, setBusy, setStage, setError } =
    useChunkerSession();
  const importInputRef = useRef<HTMLInputElement>(null);

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

  // Re-open a previously downloaded result (the full ChunkerResult JSON) and
  // render it through the same view - no re-run, no backend call.
  async function handleImport(file: File) {
    setError(null);
    try {
      const parsed = JSON.parse(await file.text()) as ChunkerResult;
      if (!parsed || !Array.isArray(parsed.blocks)) {
        throw new Error("not a chunker result file");
      }
      setStage(null);
      setResult(parsed);
    } catch (err) {
      setError(`Could not import result: ${(err as Error).message}`);
    }
  }

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
        extraControls={
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <span>Or view a previously downloaded result:</span>
            <button
              type="button"
              onClick={() => importInputRef.current?.click()}
              disabled={busy}
              className="underline hover:text-foreground disabled:opacity-50"
            >
              Import JSON
            </button>
            <input
              ref={importInputRef}
              type="file"
              accept=".json,application/json"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) handleImport(f);
                e.target.value = "";
              }}
            />
          </div>
        }
      />
      {error && <p className="text-sm text-destructive">{error}</p>}
      {result && <BlocksList result={result} />}
      {!result && !busy && !error && (
        <EmptyState message="Upload a document to begin." />
      )}
    </div>
  );
}

function formatMetaValue(v: unknown): string {
  if (Array.isArray(v)) return v.join(", ");
  if (v === null || v === undefined) return "—";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

/** Renders a provenance dict (structural_meta / style_hint) as compact
 * key=value pairs, so block parsing details are inspectable without the JSON. */
function MetaLine({ label, meta }: { label: string; meta: Record<string, unknown> }) {
  const entries = Object.entries(meta ?? {});
  if (entries.length === 0) return null;
  return (
    <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 font-mono text-[11px] text-muted-foreground/70">
      <span className="text-muted-foreground/40">{label}</span>
      {entries.map(([k, v]) => (
        <span key={k}>
          {k}=<span className="text-muted-foreground">{formatMetaValue(v)}</span>
        </span>
      ))}
    </div>
  );
}

function BlocksList({ result }: { result: ChunkerResult }) {
  const blocks = result.blocks;
  const labeledCount = blocks.filter((b) => b.section_label).length;
  return (
    <CollapsibleCard
      title={`${blocks.length} blocks`}
      subtitle={`${labeledCount} labeled`}
      trailing={
        <DownloadButton
          filename={`${result.doc_id || "chunker"}-result.json`}
          data={result}
          format="json"
          label="Download JSON"
        />
      }
    >
      <ul className="-mx-6 divide-y divide-border">
        {blocks.map((block: ContentBlock) => (
          <li key={block.id} className="px-6 py-4">
            <details className="group/block">
              <summary className="flex cursor-pointer flex-wrap items-center gap-2 text-xs text-muted-foreground [&::-webkit-details-marker]:hidden">
                <Badge variant="outline">{block.block_type}</Badge>
                {block.section_label && <Badge variant="muted">{block.section_label}</Badge>}
                <span className="font-mono">{block.id}</span>
                <ChevronDown className="ml-auto h-4 w-4 shrink-0 text-muted-foreground transition-transform group-open/block:rotate-180" />
              </summary>
              <div className="mt-2 space-y-0.5 rounded-md bg-muted/40 px-3 py-2 font-mono text-[11px] text-muted-foreground/70">
                <div>
                  <span className="text-muted-foreground/40">ordinal</span> #{block.ordinal}
                </div>
                <div>
                  <span className="text-muted-foreground/40">stack</span>{" "}
                  {block.heading_stack.length > 0
                    ? block.heading_stack.join(" › ")
                    : "(top level)"}
                </div>
                <MetaLine label="meta" meta={block.structural_meta} />
                <MetaLine label="style" meta={block.style_hint} />
              </div>
            </details>
            <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed">{block.content}</p>
          </li>
        ))}
      </ul>
    </CollapsibleCard>
  );
}
