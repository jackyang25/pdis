"use client";

import { PageHeader } from "@/components/page-header";
import { MultiRunPanel } from "@/components/multi-run-panel";
import { HeaderGuard } from "@/components/header-guard";
import { EmptyState } from "@/components/empty-state";
import { CollapsibleCard } from "@/components/collapsible-card";
import { DownloadButton } from "@/components/download-button";
import { Badge } from "@/components/ui/badge";
import { runMonitor, type Header, type Match, type MonitorResponse } from "@/lib/api";
import { useMonitorSession } from "@/lib/session";

const MONITOR_STEPS = [
  { key: "parse", label: "Parsing documents" },
  { key: "queries", label: "Extracting queries" },
  { key: "search", label: "Searching the web" },
  { key: "insights", label: "Extracting insights" },
  { key: "classify", label: "Detecting drift" },
];

const RELATION_ORDER: Record<Match["relation"], number> = {
  contradicts: 0,
  extends: 1,
  confirms: 2,
  unrelated: 3,
};

const RELATION_VARIANT: Record<Match["relation"], "default" | "outline" | "muted"> = {
  contradicts: "default",
  extends: "outline",
  confirms: "muted",
  unrelated: "outline",
};

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
      {result && <MatchesList result={result} />}
      {!result && !busy && !error && (
        <EmptyState message="Upload one or more documents to begin." />
      )}
    </div>
  );
}

function MatchesList({ result }: { result: MonitorResponse }) {
  const matches = result.matches ?? [];
  if (matches.length === 0) {
    return <EmptyState message="No matches were produced from this run." />;
  }

  const sorted = [...matches].sort(
    (a, b) => RELATION_ORDER[a.relation] - RELATION_ORDER[b.relation],
  );
  const counts = sorted.reduce<Record<string, number>>((acc, match) => {
    acc[match.relation] = (acc[match.relation] || 0) + 1;
    return acc;
  }, {});

  return (
    <div className="flex flex-col gap-4">
      <CollapsibleCard
        title={`${matches.length} match${matches.length === 1 ? "" : "es"}`}
        subtitle={["contradicts", "extends", "confirms", "unrelated"]
          .filter((relation) => counts[relation])
          .map((relation) => `${counts[relation]} ${relation}`)
          .join(" · ")}
        trailing={
          <DownloadButton
            filename="matches.jsonl"
            data={matches}
            format="jsonl"
            label="Download JSONL"
          />
        }
      >
        <ul className="-mx-6 divide-y divide-border">
          {sorted.map((match, index) => (
            <li key={index} className="px-6 py-4">
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <Badge variant={RELATION_VARIANT[match.relation]}>
                  {match.relation}
                </Badge>
                {match.insight.section_label && (
                  <Badge variant="outline">{match.insight.section_label}</Badge>
                )}
                <span className="break-words text-xs text-muted-foreground">
                  {match.insight.query}
                </span>
              </div>
              <p className="text-sm leading-relaxed">{match.insight.statement}</p>
              {match.reason && (
                <p className="mt-1 text-xs italic text-muted-foreground">
                  {match.reason}
                </p>
              )}
              {match.insight.supporting_findings.length > 0 && (
                <ul className="mt-2 space-y-1">
                  {match.insight.supporting_findings.map((finding) => (
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
      </CollapsibleCard>
    </div>
  );
}
