"use client";

import { useMemo } from "react";
import { PageHeader } from "@/components/page-header";
import { RunPanel } from "@/components/run-panel";
import { HeaderGuard } from "@/components/header-guard";
import { EmptyState } from "@/components/empty-state";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { DownloadButton } from "@/components/download-button";
import { CollapsibleCard } from "@/components/collapsible-card";
import { runBenchmarker, type Claim, type Header } from "@/lib/api";
import { useBenchmarkerSession } from "@/lib/session";

export default function EvidencePage() {
  return (
    <>
      <PageHeader
        title="Benchmarker"
        description="Extract source-backed claims from a product profile document to build the peer corpus."
      />
      <HeaderGuard>{(header) => <EvidenceView header={header as Header} />}</HeaderGuard>
    </>
  );
}

const EVIDENCE_STEPS = [
  { key: "parse", label: "Parse document" },
  { key: "extract", label: "Extract claims" },
  { key: "bind", label: "Bind to attributes" },
  { key: "appraise", label: "Appraise strength" },
];

function EvidenceView({ header }: { header: Header }) {
  const { result, busy, stage, error, setResult, setBusy, setStage, setError } =
    useBenchmarkerSession();

  async function handleRun(file: File) {
    setBusy(true);
    setError(null);
    setStage(null);
    try {
      const res = await runBenchmarker(file, header, setStage);
      setResult(res);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const claims = result?.claims ?? null;

  return (
    <div className="flex flex-col gap-6">
      <RunPanel
        accept=".docx,.pdf"
        busy={busy}
        onRun={handleRun}
        steps={EVIDENCE_STEPS}
        currentStage={stage}
      />
      {error && <p className="text-sm text-destructive">{error}</p>}
      {claims && <ClaimsList claims={claims} />}
      {!claims && !busy && !error && (
        <EmptyState message="Upload a .docx or .pdf to begin." />
      )}
    </div>
  );
}

function ClaimsList({ claims }: { claims: Claim[] }) {
  const byAttr = useMemo(() => groupByAttribute(claims), [claims]);
  const sourceId = claims[0]?.source_id ?? "claims";
  const unbound = byAttr.get("unbound")?.length ?? 0;
  const boundAttrCount = unbound ? byAttr.size - 1 : byAttr.size;
  return (
    <CollapsibleCard
      title={`${claims.length} claims`}
      subtitle={`${boundAttrCount} attributes bound · ${unbound} unbound`}
      trailing={
        <DownloadButton
          filename={`${sourceId}_claims.jsonl`}
          data={claims}
          format="jsonl"
          label="Download JSONL"
        />
      }
    >
      <div className="-mx-6 divide-y divide-border">
        {Array.from(byAttr.entries()).map(([attr, group]) => (
          <section key={attr} className="px-6 py-4">
            <div className="mb-3 flex items-center gap-2">
              <h3 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                {attr}
              </h3>
              <span className="text-xs text-muted-foreground">{group.length}</span>
            </div>
            <ul className="flex flex-col gap-3">
              {group.map((claim) => (
                <li key={claim.id || claim.statement} className="rounded-md bg-secondary/40 px-4 py-3">
                  <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    <Badge variant="outline">{claim.claim_type}</Badge>
                    <Badge variant="muted">{claim.polarity}</Badge>
                  </div>
                  <p className="mt-2 text-sm leading-relaxed">{claim.statement}</p>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </CollapsibleCard>
  );
}

function groupByAttribute(claims: Claim[]): Map<string, Claim[]> {
  const out = new Map<string, Claim[]>();
  for (const claim of claims) {
    const key = claim.attribute_ref ?? "unbound";
    const list = out.get(key) ?? [];
    list.push(claim);
    out.set(key, list);
  }
  return out;
}
