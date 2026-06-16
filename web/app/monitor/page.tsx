"use client";

import { PageHeader } from "@/components/page-header";
import { MultiRunPanel } from "@/components/multi-run-panel";
import { HeaderGuard } from "@/components/header-guard";
import { EmptyState } from "@/components/empty-state";
import { CollapsibleCard } from "@/components/collapsible-card";
import { DownloadButton } from "@/components/download-button";
import { Badge } from "@/components/ui/badge";
import {
  runMonitor,
  type EvidenceAssessment,
  type Header,
  type Match,
  type MonitorResponse,
} from "@/lib/api";
import { useMonitorSession } from "@/lib/session";

const MONITOR_STEPS = [
  { key: "parse", label: "Parsing documents" },
  { key: "queries", label: "Extracting queries" },
  { key: "search", label: "Searching the web" },
  { key: "insights", label: "Extracting insights" },
  { key: "classify", label: "Detecting drift" },
  { key: "evidence", label: "Assessing evidence" },
];

const RELATION_ORDER: Record<Match["relation"], number> = {
  contradicts: 0,
  extends: 1,
  confirms: 2,
  unrelated: 3,
};

type Status = "conflict" | "updates" | "confirmed" | "clear";

const STATUS_RANK: Record<Status, number> = {
  conflict: 0,
  updates: 1,
  confirmed: 2,
  clear: 3,
};

const STATUS_META: Record<
  Status,
  {
    label: string;
    tone: string;
    badge: "default" | "outline" | "muted";
  }
> = {
  conflict: {
    label: "Conflict",
    tone: "border-l-red-500 bg-red-50/50",
    badge: "default",
  },
  updates: {
    label: "Updates",
    tone: "border-l-amber-400 bg-amber-50/50",
    badge: "outline",
  },
  confirmed: {
    label: "Confirmed",
    tone: "border-l-emerald-500 bg-emerald-50/50",
    badge: "muted",
  },
  clear: {
    label: "Clear",
    tone: "border-l-transparent bg-transparent",
    badge: "outline",
  },
};

const EVIDENCE_META: Record<
  EvidenceAssessment["strength"],
  { label: string; className: string }
> = {
  well_grounded: {
    label: "Well grounded",
    className: "border-emerald-200 bg-emerald-50 text-emerald-700",
  },
  partial: {
    label: "Partial evidence",
    className: "border-blue-200 bg-blue-50 text-blue-700",
  },
  thin: {
    label: "Thin evidence",
    className: "border-amber-200 bg-amber-50 text-amber-700",
  },
  unsupported: {
    label: "Unsupported",
    className: "border-red-200 bg-red-50 text-red-700",
  },
  unknown: {
    label: "Unknown evidence",
    className: "border-transparent bg-muted text-muted-foreground",
  },
};

const BASIS_LABELS: Record<string, string> = {
  standard_of_care: "Standard of care",
  modeling: "Modeling",
  study_strength: "Study strength",
  regulatory_precedent: "Regulatory precedent",
};

function attributeLabel(ref: string) {
  const local = ref.includes(".") ? ref.split(".").slice(1).join(".") : ref;
  return local
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

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
      {result && <FieldGrid result={result} />}
      {!result && !busy && !error && (
        <EmptyState message="Upload one or more documents to begin." />
      )}
    </div>
  );
}

function statusFor(matches: Match[]): Status {
  if (matches.some((match) => match.relation === "contradicts")) return "conflict";
  if (matches.some((match) => match.relation === "extends")) return "updates";
  if (matches.some((match) => match.relation === "confirms")) return "confirmed";
  return "clear";
}

function FieldGrid({ result }: { result: MonitorResponse }) {
  const matches = result.matches ?? [];
  const variables = result.variables ?? [];

  if (variables.length === 0) {
    return <EmptyState message="No variables were returned for this intervention." />;
  }

  const matchesByVariable = new Map<string, Match[]>();
  for (const match of matches) {
    const ref = match.insight.attribute_ref;
    if (!ref) continue;
    if (!matchesByVariable.has(ref)) matchesByVariable.set(ref, []);
    matchesByVariable.get(ref)!.push(match);
  }
  const assessmentsByVariable = new Map<string, EvidenceAssessment>();
  for (const assessment of result.assessments ?? []) {
    assessmentsByVariable.set(assessment.attribute_ref, assessment);
  }

  const rows = variables
    .map((variable) => {
      const variableMatches = matchesByVariable.get(variable.name) ?? [];
      const sortedMatches = [...variableMatches].sort(
        (a, b) => RELATION_ORDER[a.relation] - RELATION_ORDER[b.relation],
      );
      const status = statusFor(sortedMatches);
      return {
        variable,
        matches: sortedMatches,
        status,
        assessment: assessmentsByVariable.get(variable.name) ?? null,
      };
    })
    .sort(
      (a, b) =>
        STATUS_RANK[a.status] - STATUS_RANK[b.status] ||
        attributeLabel(a.variable.name).localeCompare(attributeLabel(b.variable.name)),
    );

  const updatedCount = rows.filter(
    (row) => row.status === "conflict" || row.status === "updates",
  ).length;
  const counts = rows.reduce<Record<Status, number>>(
    (acc, row) => {
      acc[row.status] += 1;
      return acc;
    },
    { conflict: 0, updates: 0, confirmed: 0, clear: 0 },
  );

  return (
    <div className="flex flex-col gap-4">
      <CollapsibleCard
        title={`${variables.length} fields`}
        subtitle={`${result.stats?.unique_findings ?? 0} sources · ${
          result.stats?.insights ?? 0
        } insights · ${updatedCount} updates · ${counts.clear} clear`}
        trailing={
          <DownloadButton
            filename="matches.jsonl"
            data={matches}
            format="jsonl"
            label="Download JSONL"
          />
        }
      >
        <div className="-mx-6">
          {rows.map((row) => (
            <FieldRow
              key={row.variable.name}
              name={row.variable.name}
              description={row.variable.description}
              status={row.status}
              matches={row.matches}
              assessment={row.assessment}
            />
          ))}
        </div>
      </CollapsibleCard>
    </div>
  );
}

function FieldRow({
  name,
  description,
  status,
  matches,
  assessment,
}: {
  name: string;
  description: string;
  status: Status;
  matches: Match[];
  assessment: EvidenceAssessment | null;
}) {
  const meta = STATUS_META[status];
  const evidenceMeta = assessment ? EVIDENCE_META[assessment.strength] : null;

  return (
    <details className={`group border-b border-b-border border-l-4 ${meta.tone}`}>
      <summary className="flex cursor-pointer items-start justify-between gap-4 px-6 py-4 [&::-webkit-details-marker]:hidden">
        <div className="min-w-0 flex-1">
          <div className="mb-1 flex flex-wrap items-center gap-2">
            <Badge variant={meta.badge}>{meta.label}</Badge>
            {assessment && evidenceMeta && (
              <Badge variant="outline" className={evidenceMeta.className}>
                {evidenceMeta.label}
              </Badge>
            )}
            <h3 className="text-sm font-medium">{attributeLabel(name)}</h3>
            <span className="text-xs text-muted-foreground">
              {matches.length} match{matches.length === 1 ? "" : "es"}
            </span>
          </div>
          <p className="mt-2 mb-3 line-clamp-2 text-xs leading-relaxed text-muted-foreground">
            {description}
          </p>
        </div>
        <span className="shrink-0 text-xs text-muted-foreground group-open:hidden">
          Expand
        </span>
        <span className="hidden shrink-0 text-xs text-muted-foreground group-open:inline">
          Collapse
        </span>
      </summary>

      <div className="px-6 pb-4">
        {assessment && (
          <div className="mb-4 rounded-md bg-card p-4">
            <p className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
              Evidence
            </p>
            {assessment.basis.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {assessment.basis.map((basis) => (
                  <Badge key={basis} variant="outline">
                    {BASIS_LABELS[basis] ?? basis}
                  </Badge>
                ))}
              </div>
            )}
            <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
              {assessment.reason}
            </p>
            {assessment.supporting_findings.length > 0 && (
              <ul className="mt-2 space-y-1">
                {assessment.supporting_findings.map((finding) => (
                  <li key={finding.url} className="text-xs text-muted-foreground">
                    <span className="inline-flex flex-wrap items-center gap-1.5">
                      <a
                        href={finding.url}
                        target="_blank"
                        rel="noreferrer"
                        className="underline hover:text-foreground"
                      >
                        {finding.title || finding.url}
                      </a>
                      {finding.source === "pubmed" && (
                        <Badge variant="outline" className="text-[10px]">
                          PubMed
                        </Badge>
                      )}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
        {matches.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No matches for this variable.
          </p>
        ) : (
          <ul className="space-y-4">
            {matches.map((match, index) => (
              <li key={index} className="rounded-md border border-border bg-card p-4">
                <div className="mb-3 flex flex-wrap items-center gap-2">
                  <Badge variant="outline">{match.relation}</Badge>
                </div>
                <div>
                  <p className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                    Found
                  </p>
                  <p className="mt-1 text-sm font-medium leading-relaxed text-foreground">
                    {match.insight.statement}
                  </p>
                </div>
                {match.reason && (
                  <div className="mt-3 border-l-2 border-border pl-3">
                    <p className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                      Why it matters
                    </p>
                    <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                      {match.reason}
                    </p>
                  </div>
                )}
                {match.insight.supporting_findings.length > 0 && (
                  <ul className="mt-3 space-y-1">
                    {match.insight.supporting_findings.map((finding) => (
                      <li key={finding.url} className="text-xs text-muted-foreground">
                        <span className="inline-flex flex-wrap items-center gap-1.5">
                          <a
                            href={finding.url}
                            target="_blank"
                            rel="noreferrer"
                            className="underline hover:text-foreground"
                          >
                            {finding.title || finding.url}
                          </a>
                          {finding.source === "pubmed" && (
                            <Badge variant="outline" className="text-[10px]">
                              PubMed
                            </Badge>
                          )}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
                <p className="mt-2 truncate text-[11px] text-muted-foreground/70">
                  searched: {match.insight.query}
                </p>
              </li>
            ))}
          </ul>
        )}
      </div>
    </details>
  );
}
