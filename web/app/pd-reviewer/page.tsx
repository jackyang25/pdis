"use client";

import { useMemo, useState } from "react";
import { PageHeader } from "@/components/page-header";
import { RunPanel } from "@/components/run-panel";
import { HeaderGuard } from "@/components/header-guard";
import { EmptyState } from "@/components/empty-state";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import {
  runPDReviewer,
  type Header,
  type PDReviewerResponse,
  type PeerClaim,
  type SectionGrade,
} from "@/lib/api";

export default function PDReviewerPage() {
  return (
    <>
      <PageHeader
        title="PD Reviewer"
        description="Grade a document against a TPP rubric, benchmarked against peer claims."
      />
      <HeaderGuard>{(header) => <ReviewerView header={header as Header} />}</HeaderGuard>
    </>
  );
}

function ReviewerView({ header }: { header: Header }) {
  const [result, setResult] = useState<PDReviewerResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleRun(file: File) {
    setBusy(true);
    setError(null);
    try {
      const res = await runPDReviewer(file, header, { usePeerClaims: true });
      setResult(res);
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
      {result && (
        <>
          <OverallCard grade={result.review.overall_grade} docId={result.review.doc_id} />
          <PeerClaimsCard peerClaims={result.peer_claims} />
          <TopIssuesCard issues={result.review.top_issues} />
          <SectionsCard sections={result.review.section_grades} />
        </>
      )}
      {!result && !busy && !error && (
        <EmptyState message="Upload a .docx to begin." />
      )}
    </div>
  );
}

function OverallCard({ grade, docId }: { grade: string; docId: string }) {
  return (
    <div className="flex items-center justify-between rounded-lg border border-border bg-card px-6 py-5">
      <div>
        <div className="text-xs uppercase tracking-wide text-muted-foreground">Overall grade</div>
        <div className="mt-1 font-mono text-sm">{docId}</div>
      </div>
      <div className="text-4xl font-semibold tabular-nums">{grade}</div>
    </div>
  );
}

function TopIssuesCard({ issues }: { issues: string[] }) {
  if (issues.length === 0) return null;
  return (
    <section className="rounded-lg border border-border bg-card">
      <div className="px-6 py-4">
        <h2 className="text-sm font-semibold">Top issues</h2>
      </div>
      <Separator />
      <ol className="divide-y divide-border">
        {issues.map((issue, idx) => (
          <li key={idx} className="px-6 py-3 text-sm">
            {issue}
          </li>
        ))}
      </ol>
    </section>
  );
}

function SectionsCard({ sections }: { sections: SectionGrade[] }) {
  return (
    <section className="rounded-lg border border-border bg-card">
      <div className="px-6 py-4">
        <h2 className="text-sm font-semibold">Section breakdown</h2>
      </div>
      <Separator />
      <ul className="divide-y divide-border">
        {sections.map((section) => (
          <li key={section.section_name} className="px-6 py-4">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-sm font-medium">{section.section_name}</div>
                {!section.is_present && (
                  <div className="mt-1 text-xs text-muted-foreground">Missing</div>
                )}
              </div>
              <span className="font-mono text-lg tabular-nums">{section.grade}</span>
            </div>
            {section.recommendation && (
              <p className="mt-2 text-sm text-muted-foreground">{section.recommendation}</p>
            )}
            {section.missing_variables.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {section.missing_variables.map((v) => (
                  <Badge key={v} variant="outline">
                    {v}
                  </Badge>
                ))}
              </div>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

function PeerClaimsCard({ peerClaims }: { peerClaims: PeerClaim[] }) {
  const byAttr = useMemo(() => {
    const m = new Map<string, PeerClaim[]>();
    for (const c of peerClaims) {
      const key = c.attribute_ref ?? "unbound";
      const list = m.get(key) ?? [];
      list.push(c);
      m.set(key, list);
    }
    return m;
  }, [peerClaims]);
  if (peerClaims.length === 0) return null;
  const docs = new Set(peerClaims.map((c) => c.source_id));
  return (
    <section className="rounded-lg border border-border bg-card">
      <div className="flex items-center justify-between px-6 py-4">
        <h2 className="text-sm font-semibold">Peer benchmark</h2>
        <span className="text-xs text-muted-foreground">
          {peerClaims.length} claims · {docs.size} peer docs · {byAttr.size} attributes
        </span>
      </div>
      <Separator />
      <div className="divide-y divide-border">
        {Array.from(byAttr.entries()).map(([attr, group]) => (
          <section key={attr} className="px-6 py-4">
            <div className="mb-2 flex items-center gap-2">
              <h3 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                {attr}
              </h3>
              <span className="text-xs text-muted-foreground">{group.length}</span>
            </div>
            <ul className="flex flex-col gap-2">
              {group.slice(0, 5).map((c, idx) => (
                <li key={idx} className="text-sm">
                  <span className="font-mono text-xs text-muted-foreground">{c.source_id}</span>
                  <span className="ml-2">{c.statement}</span>
                </li>
              ))}
              {group.length > 5 && (
                <li className="text-xs text-muted-foreground">
                  +{group.length - 5} more
                </li>
              )}
            </ul>
          </section>
        ))}
      </div>
    </section>
  );
}
