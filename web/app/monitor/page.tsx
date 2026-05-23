"use client";

import { PageHeader } from "@/components/page-header";
import { MultiRunPanel } from "@/components/multi-run-panel";
import { HeaderGuard } from "@/components/header-guard";
import { EmptyState } from "@/components/empty-state";
import { CollapsibleCard } from "@/components/collapsible-card";
import { DownloadButton } from "@/components/download-button";
import { runMonitor, type Header, type MonitorResponse } from "@/lib/api";
import { useMonitorSession } from "@/lib/session";

const MONITOR_STEPS = [
  { key: "parse", label: "Parse documents" },
  { key: "queries", label: "Extract queries" },
  { key: "search", label: "Search the web" },
  { key: "insights", label: "Extract insights" },
];

export default function MonitorPage() {
  return (
    <>
      <PageHeader
        title="Monitor"
        description="Upload one or more documents. Monitor searches the web for relevant updates and extracts grounded Insights."
      />
      <HeaderGuard>{(header) => <MonitorView header={header as Header} />}</HeaderGuard>
    </>
  );
}

function MonitorView({ header }: { header: Header }) {
  const { result, busy, stage, error, setResult, setBusy, setStage, setError } =
    useMonitorSession();

  async function handleRun(files: File[]) {
    setBusy(true);
    setError(null);
    setStage(null);
    try {
      const res = await runMonitor(files, header, setStage);
      setResult(res);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <MultiRunPanel
        accept=".docx,.pdf"
        busy={busy}
        onRun={handleRun}
        steps={MONITOR_STEPS}
        currentStage={stage}
      />
      {error && <p className="text-sm text-destructive">{error}</p>}
      {result && <InsightsList result={result} />}
      {!result && !busy && !error && (
        <EmptyState message="Upload one or more documents to begin." />
      )}
    </div>
  );
}

function InsightsList({ result }: { result: MonitorResponse }) {
  const insights = result.insights ?? [];
  if (insights.length === 0) {
    return <EmptyState message="No insights were extracted from the search results." />;
  }

  const byQuery = new Map<string, typeof insights>();
  for (const insight of insights) {
    const key = insight.query || "(unattributed)";
    if (!byQuery.has(key)) byQuery.set(key, []);
    byQuery.get(key)!.push(insight);
  }

  return (
    <div className="flex flex-col gap-4">
      <CollapsibleCard
        title={`${insights.length} insight${insights.length === 1 ? "" : "s"}`}
        subtitle={`${byQuery.size} quer${byQuery.size === 1 ? "y" : "ies"}`}
        trailing={
          <DownloadButton
            filename="insights.jsonl"
            data={insights}
            format="jsonl"
            label="Download JSONL"
          />
        }
      >
        <div className="-mx-6 divide-y divide-border">
          {Array.from(byQuery.entries()).map(([query, group]) => (
            <section key={query} className="px-6 py-4">
              <h3 className="mb-3 break-words text-xs font-medium uppercase tracking-wide text-muted-foreground">
                {query}
              </h3>
              <ul className="space-y-4">
                {group.map((insight, index) => (
                  <li key={`${query}-${index}`}>
                    <p className="text-sm leading-relaxed">{insight.statement}</p>
                    {insight.supporting_findings &&
                      insight.supporting_findings.length > 0 && (
                        <ul className="mt-2 space-y-1">
                          {insight.supporting_findings.map((finding) => (
                            <li key={finding.url} className="text-xs text-muted-foreground">
                              <a
                                href={finding.url}
                                target="_blank"
                                rel="noreferrer"
                                className="underline hover:text-foreground"
                              >
                                {finding.title || finding.url}
                              </a>
                            </li>
                          ))}
                        </ul>
                      )}
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      </CollapsibleCard>
    </div>
  );
}
