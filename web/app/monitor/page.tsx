"use client";

import { useRef, useState } from "react";
import { PageHeader } from "@/components/page-header";
import { MultiRunPanel } from "@/components/multi-run-panel";
import { HeaderGuard } from "@/components/header-guard";
import { EmptyState } from "@/components/empty-state";
import { CollapsibleCard } from "@/components/collapsible-card";
import { DownloadButton } from "@/components/download-button";
import {
  runMonitor,
  type Conformity,
  type EvidenceAssessment,
  type Finding,
  type Header,
  type Match,
  type MonitorResponse,
  type PrecedentSignal,
} from "@/lib/api";
import { useMonitorSession } from "@/lib/session";

const MONITOR_STEPS = [
  { key: "parse", label: "Parsing documents" },
  { key: "queries", label: "Extracting queries" },
  { key: "search", label: "Searching the web" },
  { key: "insights", label: "Extracting insights" },
  { key: "classify", label: "Detecting drift" },
  { key: "evidence", label: "Assessing evidence" },
  { key: "conformity", label: "Scoring conformity" },
  { key: "precedent", label: "Checking precedent" },
];

const SOURCE_LIST_LIMIT = 5;

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

// --- Tone tokens: one dot color per signal value. Only the field stripe is
// "filled" color; every chip uses the same shape + a small dot, so appearance
// encodes severity without competing fills. ---
const NEUTRAL_DOT = "bg-muted-foreground/40";

const STATUS_META: Record<Status, { label: string; dot: string; stripe: string }> = {
  conflict: { label: "Conflict", dot: "bg-red-500", stripe: "border-l-red-500" },
  updates: { label: "Updates", dot: "bg-amber-400", stripe: "border-l-amber-400" },
  confirmed: { label: "Confirmed", dot: "bg-emerald-500", stripe: "border-l-emerald-500" },
  clear: { label: "Clear", dot: NEUTRAL_DOT, stripe: "border-l-border" },
};

const EVIDENCE_META: Record<EvidenceAssessment["strength"], { label: string; dot: string }> = {
  well_grounded: { label: "Well grounded", dot: "bg-emerald-500" },
  partial: { label: "Partial evidence", dot: "bg-blue-500" },
  thin: { label: "Thin evidence", dot: "bg-amber-400" },
  unsupported: { label: "Unsupported", dot: "bg-red-500" },
  unknown: { label: "Unknown", dot: NEUTRAL_DOT },
};

const RELATION_DOT: Record<Match["relation"], string> = {
  contradicts: "bg-red-500",
  extends: "bg-amber-400",
  confirms: "bg-emerald-500",
  unrelated: NEUTRAL_DOT,
};

const BASIS_LABELS: Record<string, string> = {
  standard_of_care: "Standard of care",
  modeling: "Modeling",
  study_strength: "Study strength",
  regulatory_precedent: "Regulatory precedent",
};

const SOURCE_TYPE_LABELS: Record<string, string> = {
  systematic_review_meta_analysis: "Meta-analysis",
  rct_phase3: "Phase 3 RCT",
  rct_phase2: "Phase 2 RCT",
  regulatory_assessment: "Regulatory assessment",
  clinical_trial_registry: "Trial registry",
  observational_study: "Observational study",
  program_effectiveness: "Program effectiveness",
  preprint: "Preprint",
  press_release: "Press release",
  other: "Other source",
};

// Conformity is a position (target vs current evidence), NOT a good/bad grade:
// a low score often reflects an intentional stretch target, not a failure. So
// its chip uses a single neutral tone rather than green/red, to avoid being
// read as a pass/fail score.
const CONFORMITY_DOT = "bg-slate-400";

// Precedent is also NOT a good/bad grade - a novel target is exactly what a TPP
// is for. So established/emerging/novel/unknown share a neutral dot (the label
// carries the meaning); only `disconfirmed` (the approach was tried and failed)
// gets an attention tone, since it is the one genuine caution.
const PRECEDENT_META: Record<PrecedentSignal["precedent"], { label: string; dot: string }> = {
  established: { label: "Established", dot: NEUTRAL_DOT },
  emerging: { label: "Emerging", dot: NEUTRAL_DOT },
  novel: { label: "Novel / white space", dot: NEUTRAL_DOT },
  disconfirmed: { label: "Disconfirmed", dot: "bg-amber-400" },
  unknown: { label: "Precedent unknown", dot: NEUTRAL_DOT },
};

function formatDate(iso: string | null): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (isNaN(d.getTime())) return null;
  return d.toLocaleDateString("en-US", { year: "numeric", month: "short" });
}

function attributeLabel(ref: string) {
  const local = ref.includes(".") ? ref.split(".").slice(1).join(".") : ref;
  return local.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

function statusFor(matches: Match[]): Status {
  if (matches.some((m) => m.relation === "contradicts")) return "conflict";
  if (matches.some((m) => m.relation === "extends")) return "updates";
  if (matches.some((m) => m.relation === "confirms")) return "confirmed";
  return "clear";
}

// ---------------------------------------------------------------------------
// Shared primitives
// ---------------------------------------------------------------------------

/** One consistent chip for every signal (status / evidence / conformity /
 * relation). A dot carries severity; the shell is identical everywhere. */
function SignalChip({
  dot,
  title,
  children,
}: {
  dot: string;
  title?: string;
  children: React.ReactNode;
}) {
  return (
    <span
      title={title}
      className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border border-border bg-background px-2 py-0.5 text-xs text-foreground"
    >
      <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${dot}`} />
      {children}
    </span>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
      {children}
    </p>
  );
}

type RelationCounts = Record<Match["relation"], number>;

const RELATION_BAR_ORDER: { key: Match["relation"]; color: string }[] = [
  { key: "contradicts", color: "bg-red-500" },
  { key: "extends", color: "bg-amber-400" },
  { key: "confirms", color: "bg-emerald-500" },
  { key: "unrelated", color: "bg-muted-foreground/30" },
];

function relationCounts(matches: Match[]): RelationCounts {
  return matches.reduce(
    (acc, m) => {
      acc[m.relation] += 1;
      return acc;
    },
    { contradicts: 0, extends: 0, confirms: 0, unrelated: 0 } as RelationCounts,
  );
}

function relationSummary(counts: RelationCounts): string {
  return RELATION_BAR_ORDER.filter(({ key }) => counts[key] > 0)
    .map(({ key }) => `${counts[key]} ${key}`)
    .join(" · ");
}

/** Thin stacked bar showing the field's relation mix, so the worst-case Status
 * label can't hide the distribution (1-of-18 vs 15-of-18 contradicts). */
function RelationBar({ counts }: { counts: RelationCounts }) {
  const total = RELATION_BAR_ORDER.reduce((sum, { key }) => sum + counts[key], 0);
  if (total === 0) return null;
  return (
    <span
      title={relationSummary(counts)}
      className="inline-flex h-1.5 w-20 overflow-hidden rounded-full bg-muted"
    >
      {RELATION_BAR_ORDER.filter(({ key }) => counts[key] > 0).map(({ key, color }) => (
        <span
          key={key}
          className={color}
          style={{ width: `${(counts[key] / total) * 100}%` }}
        />
      ))}
    </span>
  );
}

/** Tidy, one-line-per-row source list. Titles truncate (never wrap), metadata
 * is muted and right of the title; long lists collapse. Used everywhere a
 * finding list appears, so sources look identical across the view. */
function SourceList({ findings }: { findings: Finding[] }) {
  const [showAll, setShowAll] = useState(false);
  if (findings.length === 0) return null;
  const shown = showAll ? findings : findings.slice(0, SOURCE_LIST_LIMIT);
  return (
    <ul className="mt-2 space-y-1">
      {shown.map((f) => {
        const date = formatDate(f.published_at);
        const sourceLabel =
          f.source === "pubmed" ? "PubMed" : f.source === "clinicaltrials" ? "Registry" : "Web";
        const meta = [sourceLabel, date].filter(Boolean).join(" · ");
        return (
          <li key={f.url} className="flex items-baseline gap-2 text-xs">
            <a
              href={f.url}
              target="_blank"
              rel="noreferrer"
              title={f.title || f.url}
              className="min-w-0 flex-1 truncate text-muted-foreground underline hover:text-foreground"
            >
              {f.title || f.url}
            </a>
            <span className="shrink-0 text-[11px] text-muted-foreground/60">{meta}</span>
          </li>
        );
      })}
      {findings.length > SOURCE_LIST_LIMIT && (
        <li>
          <button
            type="button"
            onClick={() => setShowAll((v) => !v)}
            className="text-[11px] text-muted-foreground underline hover:text-foreground"
          >
            {showAll ? "Show fewer" : `Show all ${findings.length} sources`}
          </button>
        </li>
      )}
    </ul>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

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
  const {
    result,
    busy,
    stage,
    progress,
    error,
    setResult,
    setBusy,
    setStage,
    setProgress,
    setError,
  } = useMonitorSession();

  const importInputRef = useRef<HTMLInputElement>(null);

  async function handleRun(files: File[]) {
    setBusy(true);
    setError(null);
    setStage(null);
    setProgress(null);
    try {
      const res = await runMonitor(files, header, (s, p) => {
        setStage(s);
        setProgress(p ?? null);
      });
      setResult(res);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  // Re-open a previously downloaded result (the full MonitorResponse JSON) and
  // render it through the same FieldGrid - no re-run, no backend call.
  async function handleImport(file: File) {
    setError(null);
    try {
      const parsed = JSON.parse(await file.text()) as MonitorResponse;
      if (!parsed || !Array.isArray(parsed.variables) || !Array.isArray(parsed.matches)) {
        throw new Error("not a monitor result file");
      }
      setStage(null);
      setProgress(null);
      setResult(parsed);
    } catch (err) {
      setError(`Could not import result: ${(err as Error).message}`);
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
        progress={progress}
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
      {result && <FieldGrid result={result} />}
      {!result && !busy && !error && (
        <EmptyState message="Upload one or more documents to begin." />
      )}
    </div>
  );
}

function SignalLegend({
  hasConformity,
  hasPrecedent,
}: {
  hasConformity: boolean;
  hasPrecedent: boolean;
}) {
  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-1 border-b border-border px-6 py-2.5 text-[11px] text-muted-foreground">
      <span>
        <span className="font-medium text-foreground">Status</span> — change vs your doc
      </span>
      <span>
        <span className="font-medium text-foreground">Evidence</span> — how grounded the target is
      </span>
      {hasPrecedent && (
        <span>
          <span className="font-medium text-foreground">Precedent</span> — tried before? novel = white space, not a gap
        </span>
      )}
      {hasConformity && (
        <span>
          <span className="font-medium text-foreground">Conformity</span> — target vs current evidence; low = ambitious, not bad (computed)
        </span>
      )}
      <span className="text-muted-foreground/70">
        Status, Evidence &amp; Precedent are AI judgments; Conformity is calculated.
      </span>
    </div>
  );
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
  const conformityByVariable = new Map<string, Conformity>();
  for (const score of result.conformity ?? []) {
    conformityByVariable.set(score.attribute_ref, score);
  }
  const precedentByVariable = new Map<string, PrecedentSignal>();
  for (const signal of result.precedents ?? []) {
    precedentByVariable.set(signal.attribute_ref, signal);
  }

  const rows = variables
    .map((variable) => {
      const variableMatches = matchesByVariable.get(variable.name) ?? [];
      const sortedMatches = [...variableMatches].sort(
        (a, b) => RELATION_ORDER[a.relation] - RELATION_ORDER[b.relation],
      );
      return {
        variable,
        matches: sortedMatches,
        status: statusFor(sortedMatches),
        assessment: assessmentsByVariable.get(variable.name) ?? null,
        conformity: conformityByVariable.get(variable.name) ?? null,
        precedent: precedentByVariable.get(variable.name) ?? null,
      };
    })
    .sort(
      (a, b) =>
        STATUS_RANK[a.status] - STATUS_RANK[b.status] ||
        attributeLabel(a.variable.name).localeCompare(attributeLabel(b.variable.name)),
    );

  const updatedCount = rows.filter(
    (r) => r.status === "conflict" || r.status === "updates",
  ).length;
  const clearCount = rows.filter((r) => r.status === "clear").length;
  const hasConformity = rows.some((r) => r.conformity);
  const hasPrecedent = rows.some((r) => r.precedent);

  return (
    <div className="flex flex-col gap-4">
      <CollapsibleCard
        title={`${variables.length} fields`}
        subtitle={`${result.stats?.unique_findings ?? 0} sources · ${
          result.stats?.insights ?? 0
        } insights · ${updatedCount} updated · ${clearCount} clear`}
        trailing={
          <DownloadButton
            filename="monitor-result.json"
            data={result}
            format="json"
            label="Download JSON"
          />
        }
      >
        <div className="-mx-6">
          <SignalLegend hasConformity={hasConformity} hasPrecedent={hasPrecedent} />
          {rows.map((row) => (
            <FieldRow
              key={row.variable.name}
              name={row.variable.name}
              description={row.variable.description}
              status={row.status}
              matches={row.matches}
              assessment={row.assessment}
              conformity={row.conformity}
              precedent={row.precedent}
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
  conformity,
  precedent,
}: {
  name: string;
  description: string;
  status: Status;
  matches: Match[];
  assessment: EvidenceAssessment | null;
  conformity: Conformity | null;
  precedent: PrecedentSignal | null;
}) {
  const statusMeta = STATUS_META[status];
  const evidenceMeta = assessment ? EVIDENCE_META[assessment.strength] : null;
  const precedentMeta = precedent ? PRECEDENT_META[precedent.precedent] : null;
  const counts = relationCounts(matches);

  return (
    <details className={`group border-b border-b-border border-l-4 ${statusMeta.stripe}`}>
      <summary className="flex cursor-pointer items-start justify-between gap-4 px-6 py-4 [&::-webkit-details-marker]:hidden">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline gap-x-2">
            <h3 className="text-sm font-semibold text-foreground">{attributeLabel(name)}</h3>
            <span className="text-xs text-muted-foreground">
              {matches.length} match{matches.length === 1 ? "" : "es"}
            </span>
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            <SignalChip dot={statusMeta.dot} title="Status — change vs your document (worst-case across the matches below)">
              {statusMeta.label}
            </SignalChip>
            {matches.length > 0 && <RelationBar counts={counts} />}
            {assessment && evidenceMeta && (
              <SignalChip dot={evidenceMeta.dot} title="Evidence — how grounded the target is (AI)">
                {evidenceMeta.label}
              </SignalChip>
            )}
            {precedent && precedentMeta && (
              <SignalChip dot={precedentMeta.dot} title="Precedent — has this target/approach been tried before? (AI)">
                {precedentMeta.label}
              </SignalChip>
            )}
            {conformity && (
              <SignalChip
                dot={CONFORMITY_DOT}
                title="Conformity — target vs current evidence; low = ambitious, not bad (computed)"
              >
                {Math.round(conformity.conformity * 100)}% conformity
              </SignalChip>
            )}
          </div>
          <p className="mt-2 line-clamp-2 text-xs leading-relaxed text-muted-foreground">
            {description}
          </p>
        </div>
        <span className="shrink-0 text-xs text-muted-foreground group-open:hidden">Expand</span>
        <span className="hidden shrink-0 text-xs text-muted-foreground group-open:inline">
          Collapse
        </span>
      </summary>

      <div className="space-y-4 px-6 pb-5">
        {assessment?.doc_target && (
          <div className="rounded-md border border-border bg-muted/40 px-4 py-3">
            <SectionLabel>From your document</SectionLabel>
            <p className="mt-1 text-sm leading-relaxed text-foreground">
              {assessment.doc_target}
            </p>
            <p className="mt-1 text-[11px] text-muted-foreground/70">
              Everything below is web evidence assessed against this.
            </p>
          </div>
        )}
        {conformity && <ConformityBlock conformity={conformity} />}
        {assessment && evidenceMeta && (
          <EvidenceBlock assessment={assessment} evidenceMeta={evidenceMeta} />
        )}
        {precedent && precedentMeta && (
          <PrecedentBlock precedent={precedent} precedentMeta={precedentMeta} />
        )}
        <MatchesBlock matches={matches} />
      </div>
    </details>
  );
}

function ConformityBlock({ conformity }: { conformity: Conformity }) {
  const pct = Math.round(conformity.conformity * 100);
  const lowerPct = Math.round(conformity.lower * 100);
  const upperPct = Math.round(conformity.upper * 100);
  const targetLabel =
    conformity.target_label ||
    `${conformity.comparator} ${conformity.target_value}${conformity.unit}`;

  return (
    <section className="rounded-md border border-border bg-card p-4">
      <SectionLabel>Conformity · computed</SectionLabel>
      <p className="mt-0.5 text-[11px] text-muted-foreground/80">
        How much current evidence supports your target — weighted by source quality &amp; recency.
        A <span className="text-foreground">low</span> score means your target sits above today&apos;s
        evidence, which may be intended (a stretch goal); it is a position, not a pass/fail grade.
      </p>
      <p className="mt-1 text-[11px] text-muted-foreground">
        Scored vs <span className="text-foreground">{targetLabel}</span>
      </p>

      <div className="mt-3">
        <div className="mb-1 flex items-baseline justify-between gap-2">
          <span className="text-sm font-semibold text-foreground">{pct}% likely meets target</span>
          <span className="text-xs text-muted-foreground">
            range {lowerPct}–{upperPct}%
          </span>
        </div>
        <div className="relative h-2 w-full rounded-full bg-muted">
          <div
            className="absolute h-2 rounded-full bg-foreground/20"
            style={{ left: `${lowerPct}%`, width: `${Math.max(2, upperPct - lowerPct)}%` }}
          />
          <div
            className="absolute top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full bg-foreground"
            style={{ left: `${pct}%` }}
          />
        </div>
      </div>

      <div className="mt-3">
        <SignalChip dot={CONFORMITY_DOT}>{conformity.verdict}</SignalChip>
      </div>

      {conformity.measurements.length > 0 && (
        <div className="mt-3">
          <SectionLabel>
            {conformity.measurements.length} source
            {conformity.measurements.length === 1 ? "" : "s"} combined · weighted by quality &amp; recency
          </SectionLabel>
          <ul className="mt-1 space-y-1">
            {conformity.measurements.map((m, index) => (
              <li
                key={`${m.url}-${index}`}
                className="flex items-baseline gap-2 text-xs text-muted-foreground"
              >
                {m.url ? (
                  <a
                    href={m.url}
                    target="_blank"
                    rel="noreferrer"
                    className="min-w-0 flex-1 truncate underline hover:text-foreground"
                  >
                    {SOURCE_TYPE_LABELS[m.source_type] ?? m.source_type}
                  </a>
                ) : (
                  <span className="min-w-0 flex-1 truncate">
                    {SOURCE_TYPE_LABELS[m.source_type] ?? m.source_type}
                  </span>
                )}
                <span className="shrink-0 text-[11px] text-muted-foreground/60">
                  {m.value}
                  {conformity.unit} ·{" "}
                  {m.age_months != null ? `${Math.round(m.age_months)}mo` : "date unknown"} · wt{" "}
                  {m.weight.toFixed(2)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

function EvidenceBlock({
  assessment,
  evidenceMeta,
}: {
  assessment: EvidenceAssessment;
  evidenceMeta: { label: string; dot: string };
}) {
  return (
    <section className="rounded-md border border-border bg-card p-4">
      <div className="flex items-center justify-between gap-2">
        <SectionLabel>Evidence quality · AI judgment</SectionLabel>
        <SignalChip dot={evidenceMeta.dot}>{evidenceMeta.label}</SignalChip>
      </div>
      <p className="mt-0.5 text-[11px] text-muted-foreground/80">
        How well-grounded and justified your target is
      </p>
      {assessment.reason && (
        <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{assessment.reason}</p>
      )}
      {assessment.basis.length > 0 && (
        <p className="mt-2 text-[11px] text-muted-foreground">
          <span className="text-muted-foreground/70">Basis: </span>
          {assessment.basis.map((b) => BASIS_LABELS[b] ?? b).join(" · ")}
        </p>
      )}
      <SourceList findings={assessment.supporting_findings} />
    </section>
  );
}

function PrecedentBlock({
  precedent,
  precedentMeta,
}: {
  precedent: PrecedentSignal;
  precedentMeta: { label: string; dot: string };
}) {
  return (
    <section className="rounded-md border border-border bg-card p-4">
      <div className="flex items-center justify-between gap-2">
        <SectionLabel>Precedent · AI judgment</SectionLabel>
        <SignalChip dot={precedentMeta.dot}>{precedentMeta.label}</SignalChip>
      </div>
      <p className="mt-0.5 text-[11px] text-muted-foreground/80">
        Has this target/approach been tried before? Separates a genuinely{" "}
        <span className="text-foreground">novel</span> target (white space — expected for a TPP)
        from a <span className="text-foreground">disconfirmed</span> one (tried &amp; failed). It
        reads disconfirming evidence too, so low evidence isn&apos;t mistaken for a gap.
      </p>
      {precedent.reason && (
        <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{precedent.reason}</p>
      )}
      <SourceList findings={precedent.supporting_findings} />
    </section>
  );
}

function MatchesBlock({ matches }: { matches: Match[] }) {
  if (matches.length === 0) {
    return <p className="text-sm text-muted-foreground">No matches for this variable.</p>;
  }
  return (
    <section>
      <SectionLabel>Matches · {relationSummary(relationCounts(matches))}</SectionLabel>
      <ul className="mt-2 space-y-3">
        {matches.map((match, index) => (
          <li key={index} className="rounded-md border border-border bg-card p-4">
            <SignalChip dot={RELATION_DOT[match.relation]}>{match.relation}</SignalChip>
            <p className="mt-3 text-sm font-medium leading-relaxed text-foreground">
              {match.insight.statement}
            </p>
            {match.reason && (
              <p className="mt-2 border-l-2 border-border pl-3 text-xs leading-relaxed text-muted-foreground">
                {match.reason}
              </p>
            )}
            <SourceList findings={match.insight.supporting_findings} />
            <p className="mt-2 truncate text-[11px] text-muted-foreground/60">
              searched: {match.insight.query}
            </p>
          </li>
        ))}
      </ul>
    </section>
  );
}
