"use client";

import { useMemo, useState } from "react";
import { PageHeader } from "@/components/page-header";
import { RunPanel } from "@/components/run-panel";
import { HeaderGuard } from "@/components/header-guard";
import { EmptyState } from "@/components/empty-state";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { runEvidence, type Claim, type Header } from "@/lib/api";

export default function EvidencePage() {
  return (
    <>
      <PageHeader
        title="Evidence"
        description="Extract source-backed claims from a product profile document."
      />
      <HeaderGuard>{(header) => <EvidenceView header={header as Header} />}</HeaderGuard>
    </>
  );
}

function EvidenceView({ header }: { header: Header }) {
  const [claims, setClaims] = useState<Claim[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleRun(file: File) {
    setBusy(true);
    setError(null);
    try {
      const res = await runEvidence(file, header);
      setClaims(res.claims);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <RunPanel accept=".docx,.pdf" busy={busy} onRun={handleRun} />
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
  return (
    <div className="rounded-lg border border-border bg-card">
      <div className="flex items-center justify-between px-6 py-4">
        <h2 className="text-sm font-semibold">{claims.length} claims</h2>
        <span className="text-xs text-muted-foreground">{byAttr.size} attributes</span>
      </div>
      <Separator />
      <div className="divide-y divide-border">
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
                    {claim.binding_confidence && (
                      <span>binding: {claim.binding_confidence}</span>
                    )}
                    {claim.evidence_strength && (
                      <span>strength: {claim.evidence_strength}</span>
                    )}
                  </div>
                  <p className="mt-2 text-sm leading-relaxed">{claim.statement}</p>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </div>
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
