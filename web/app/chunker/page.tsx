"use client";

import { ChevronDown } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { ErrorMessage } from "@/components/ui/error-message";
import { RunPanel } from "@/components/run-panel";
import { ConfigurationFields } from "@/components/configuration-fields";
import { HeaderGuard } from "@/components/header-guard";
import { Badge } from "@/components/ui/badge";
import { DownloadButton } from "@/components/download-button";
import { RunHistory } from "@/components/run-history";
import { runFilename, runLabel } from "@/lib/result-file";
import { BlockReferenceId } from "@/components/block-reference";
import { CollapsibleCard } from "@/components/collapsible-card";
import { runChunker, type ContentBlock, type Header } from "@/lib/api";
import { useChunkerSession, type ChunkerResult } from "@/lib/session";
import { importTool, runTool } from "@/lib/tool-run";
import { useShallow } from "zustand/react/shallow";

const CHUNKER_STEPS = [
  { key: "parse", label: "Parsing document" },
  { key: "label", label: "Labeling sections" },
];

export default function ChunkerPage() {
  return (
    <>
      <PageHeader
        title="Chunker"
        description="One document as the other tools read it: every passage they can cite, with the section each was assigned to."
      />
      <HeaderGuard>
        {(header, ready) => (
          <ChunkerView header={header as Header} ready={ready} />
        )}
      </HeaderGuard>
    </>
  );
}

function ChunkerView({ header, ready }: { header: Header; ready: boolean }) {
  const { result, busy, stage, error, startedAt } = useChunkerSession(
    useShallow(({ result, busy, stage, error, startedAt }) => ({ result, busy, stage, error, startedAt })),
  );

  return (
    <div className="flex flex-col gap-6">
      <RunPanel
        configuration={<ConfigurationFields />}
        busy={busy}
        startedAt={startedAt}
        onRun={(files) => void runTool(useChunkerSession, (report) => runChunker(files.document, header, report))}
        steps={CHUNKER_STEPS}
        currentStage={stage}
        runDisabled={!ready}
        hint={ready ? undefined : "Complete the configuration to run."}
        runLabel="Parse document"
        busyLabel="Parsing"
        // Re-open a previously downloaded result (the full ChunkerResult JSON) and
        // render it through the same view - no re-run, no backend call.
        onImport={(file) => importTool(useChunkerSession, file, readChunkerResult)}
      />
      {error && <ErrorMessage>{error}</ErrorMessage>}
      {result && <BlocksList result={result} />}
    </div>
  );
}

function readChunkerResult(raw: unknown): ChunkerResult {
  const parsed = raw as ChunkerResult | null;
  if (!parsed || !Array.isArray(parsed.blocks)) throw new Error("not a chunker result file");
  return parsed;
}

function formatMetaValue(v: unknown): string {
  if (Array.isArray(v)) return v.join(", ");
  if (v === null || v === undefined) return "—";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

/** Renders a provenance dict (structural_meta / style_hint) as compact
 * key=value pairs, so block parsing details are inspectable without the JSON. */
function MetaLine({
  label,
  meta,
}: {
  label: string;
  meta: Record<string, unknown>;
}) {
  const entries = Object.entries(meta ?? {});
  if (entries.length === 0) return null;
  return (
    <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 font-mono text-[11px] text-muted-foreground/70">
      <span className="text-muted-foreground/40">{label}</span>
      {entries.map(([k, v]) => (
        <span key={k}>
          {k}=
          <span className="text-muted-foreground">{formatMetaValue(v)}</span>
        </span>
      ))}
    </div>
  );
}

function BlocksList({ result }: { result: ChunkerResult }) {
  const { results, selectedId, selectResult, removeResult } = useChunkerSession(
    useShallow(({ results, selectedId, selectResult, removeResult }) =>
      ({ results, selectedId, selectResult, removeResult })),
  );
  const blocks = result.blocks;
  const labeledCount = blocks.filter((b) => b.section_label).length;
  return (
    <CollapsibleCard
      title={`${blocks.length} blocks`}
      subtitle={`${labeledCount} labeled`}
      flush
      trailing={
        <>
          <RunHistory
            runs={results}
            selectedId={selectedId}
            onSelect={selectResult}
            onRemove={removeResult}
            label={(value) => runLabel(value, "chunker")}
          />
          <DownloadButton
            filename={runFilename("chunker")}
            data={() => result}
            label="Download JSON"
          />
        </>
      }
    >
      {/* Flush, so the dividers meet the card's edges; a negative margin against the card's
          padding fell 4px short of them from tablet width up. */}
      <ul className="divide-y divide-border/60">
        {blocks.map((block: ContentBlock) => (
          <li key={block.id} className="px-5 py-4 sm:px-6">
            <details className="group/block">
              <summary className="flex cursor-pointer flex-wrap items-center gap-2 text-xs text-muted-foreground [&::-webkit-details-marker]:hidden">
                <Badge variant="outline">{block.block_type}</Badge>
                {block.section_label && (
                  <Badge variant="muted">{block.section_label}</Badge>
                )}
                {/* The shared compact form: the document is named in the card above, so the
                    full id repeated its name on every row. Hover and screen readers keep it. */}
                <BlockReferenceId blockId={block.id} />
                <ChevronDown className="ml-auto h-4 w-4 shrink-0 text-muted-foreground transition-transform group-open/block:rotate-180 motion-reduce:transition-none" />
              </summary>
              <div className="mt-2 space-y-0.5 rounded-md bg-foreground/[0.045] px-3 py-2 font-mono text-[11px] text-muted-foreground/70">
                <div>
                  <span className="text-muted-foreground/40">ordinal</span> #
                  {block.ordinal}
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
            {block.image ? (
              <figure className="mt-3 overflow-hidden rounded-md border border-border bg-foreground/[0.045] p-2">
                <img
                  src={`data:${block.image.media_type};base64,${block.image.data_base64}`}
                  alt={`Document figure ${block.structural_meta.image_index ?? block.ordinal}`}
                  loading="lazy"
                  decoding="async"
                  className="mx-auto max-h-[36rem] max-w-full object-contain"
                />
              </figure>
            ) : (
              <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed">
                {block.content}
              </p>
            )}
          </li>
        ))}
      </ul>
    </CollapsibleCard>
  );
}
