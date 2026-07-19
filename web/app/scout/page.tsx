"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronDown, Search } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { RunPanel } from "@/components/run-panel";
import { HeaderGuard } from "@/components/header-guard";
import { EmptyState } from "@/components/empty-state";
import { CollapsibleCard } from "@/components/collapsible-card";
import { DownloadButton } from "@/components/download-button";
import {
  runScout,
  type Conformity,
  type EvidenceAssessment,
  type Finding,
  type Header,
  type Match,
  type ScoutResponse,
  type PrecedentSignal,
} from "@/lib/api";
import { Ask } from "@/components/assistant/ask";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useScoutSession } from "@/lib/session";
import { packScoutResult, unpackScoutResult } from "@/lib/result-file";

const SCOUT_STEPS = [
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

// Tone tokens are reserved for direct signal values, never derived UI grades.
const NEUTRAL_DOT = "bg-muted-foreground/40";

const EVIDENCE_META: Record<EvidenceAssessment["strength"], { label: string; dot: string }> = {
  well_grounded: { label: "Well grounded", dot: "bg-emerald-500" },
  partial: { label: "Partial", dot: "bg-blue-500" },
  thin: { label: "Thin", dot: "bg-amber-400" },
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
  novel: { label: "Novel (white space)", dot: NEUTRAL_DOT },
  disconfirmed: { label: "Tried & failed", dot: "bg-amber-400" },
  unknown: { label: "Unknown", dot: NEUTRAL_DOT },
};

function formatDate(iso: string | null): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (isNaN(d.getTime())) return null;
  return d.toLocaleDateString("en-US", { year: "numeric", month: "short" });
}

function attributeLabel(ref: string) {
  const local = ref.includes(".") ? ref.split(".").slice(1).join(".") : ref;
  const acronyms = new Set(["cmv", "fda", "gcp", "glp", "gmp", "hiv", "hpv", "poc", "rct", "rsv", "tb", "who"]);
  return local
    .replace(/_/g, " ")
    .split(" ")
    .map((word) =>
      acronyms.has(word.toLowerCase())
        ? word.toUpperCase()
        : word.charAt(0).toUpperCase() + word.slice(1).toLowerCase(),
    )
    .join(" ");
}

function leadingRelation(matches: Match[]): Match["relation"] {
  return RELATION_ORDERED_KEYS.find((relation) =>
    matches.some((match) => match.relation === relation),
  ) ?? "unrelated";
}

// ---------------------------------------------------------------------------
// Shared primitives
// ---------------------------------------------------------------------------

/** Compact value marker used inside expanded detail sections. */
function SignalChip({
  dot,
  children,
}: {
  dot: string;
  children: React.ReactNode;
}) {
  return (
    <span className="inline-flex h-5 items-center gap-1.5 whitespace-nowrap text-[11px] font-medium text-foreground">
      <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${dot}`} />
      {children}
    </span>
  );
}

function SignalSummary({
  label,
  value,
  detail,
  dot,
}: {
  label: string;
  value: string;
  detail?: string;
  dot?: string;
}) {
  return (
    <div className="min-w-0">
      <p className="text-[11px] font-medium text-muted-foreground">{label}</p>
      <div className="mt-0.5 flex min-w-0 items-center gap-1.5 text-xs">
        {dot && <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${dot}`} />}
        <span className="truncate font-medium text-foreground">{value}</span>
        {detail && <span className="shrink-0 text-muted-foreground">· {detail}</span>}
      </div>
    </div>
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

const RELATION_ORDERED_KEYS: Match["relation"][] = [
  "contradicts",
  "extends",
  "confirms",
  "unrelated",
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
  const values = RELATION_ORDERED_KEYS.filter((key) => counts[key] > 0)
    .map((key) => `${attributeLabel(key)} ${counts[key]}`);
  return values.length > 0 ? values.join(" · ") : "No matches";
}

function countLabel(count: number, singular: string): string {
  return `${count} ${count === 1 ? singular : `${singular}s`}`;
}

/** Tidy, one-line-per-row source list. Titles truncate (never wrap), metadata
 * is muted and right of the title; long lists collapse. Used everywhere a
 * finding list appears, so sources look identical across the view. */
function SourceList({ findings }: { findings: Finding[] }) {
  const [showAll, setShowAll] = useState(false);
  if (findings.length === 0) return null;
  const shown = showAll ? findings : findings.slice(0, SOURCE_LIST_LIMIT);
  return (
    <ul className="mt-3 space-y-1.5">
      {shown.map((f) => {
        const date = formatDate(f.published_at);
        const sourceLabel =
          f.source === "pubmed" ? "PubMed" : f.source === "clinicaltrials" ? "Registry" : "Web";
        const meta = [sourceLabel, date].filter(Boolean).join(" · ");
        return (
          <li key={f.url} className="flex items-baseline gap-3 text-xs">
            <a
              href={f.url}
              target="_blank"
              rel="noreferrer"
              title={f.title || f.url}
              className="min-w-0 flex-1 truncate text-muted-foreground transition-colors hover:text-foreground hover:underline"
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

export default function ScoutPage() {
  return (
    <>
      <PageHeader title="Scout" description="Pressure-test document targets against live evidence, precedent, and quantitative conformity signals." />
      <HeaderGuard>
        {(header, ready) => <ScoutView header={header as Header} ready={ready} />}
      </HeaderGuard>
    </>
  );
}

function ScoutView({ header, ready }: { header: Header; ready: boolean }) {
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
  } = useScoutSession();

  const importInputRef = useRef<HTMLInputElement>(null);
  const [showRunPanel, setShowRunPanel] = useState(!result);

  useEffect(() => {
    if (result) setShowRunPanel(false);
  }, [result]);

  async function handleRun(file: File) {
    setBusy(true);
    setError(null);
    setStage(null);
    setProgress(null);
    try {
      const res = await runScout([file], header, (s, p) => {
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

  // Re-open a previously downloaded result (the full ScoutResponse JSON) and
  // render it through the same FieldGrid - no re-run, no backend call.
  async function handleImport(file: File) {
    setError(null);
    try {
      const parsed = unpackScoutResult(JSON.parse(await file.text()));
      if (!parsed || !Array.isArray(parsed.variables) || !Array.isArray(parsed.matches)) {
        throw new Error("not a scout result file");
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
      {(!result || showRunPanel) && (
        <RunPanel
          accept=".docx,.pdf"
          busy={busy}
          onRun={handleRun}
          steps={SCOUT_STEPS}
          currentStage={stage}
          progress={progress}
          runDisabled={!ready}
          hint={ready ? undefined : "Select org, source type & intervention in the sidebar to run."}
          extraControls={
            <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <span>Or view a previously downloaded result:</span>
              <button
                type="button"
                onClick={() => importInputRef.current?.click()}
                disabled={busy}
                className="font-medium text-primary hover:text-primary/80 disabled:opacity-50"
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
      )}
      {error && <p className="text-sm text-destructive">{error}</p>}
      {result && <FieldGrid result={result} onNewAnalysis={() => setShowRunPanel(true)} />}
      <Ask resultType="scout" result={result} />
      {!result && !busy && !error && (
        <EmptyState message="Upload a document to begin." />
      )}
    </div>
  );
}

/** True count of DISTINCT sources cited anywhere in the result (by URL).
 * Unlike stats.unique_findings (per-variable findings summed, which double-counts
 * a source cited under several variables), this counts each source once. */
function distinctSourceCount(result: ScoutResponse): number {
  const urls = new Set<string>();
  for (const m of result.matches ?? [])
    for (const f of m.insight.supporting_findings ?? []) if (f.url) urls.add(f.url);
  for (const a of result.assessments ?? [])
    for (const f of a.supporting_findings ?? []) if (f.url) urls.add(f.url);
  for (const p of result.precedents ?? [])
    for (const f of p.supporting_findings ?? []) if (f.url) urls.add(f.url);
  for (const c of result.conformity ?? [])
    for (const meas of c.measurements ?? []) if (meas.url) urls.add(meas.url);
  return urls.size;
}

function FieldGrid({ result, onNewAnalysis }: { result: ScoutResponse; onNewAnalysis: () => void }) {
  const matches = result.matches ?? [];
  const variables = result.variables ?? [];
  const [query, setQuery] = useState("");
  const [relationFilter, setRelationFilter] = useState<"all" | Match["relation"]>("all");

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
        leadingRelation: leadingRelation(sortedMatches),
        assessment: assessmentsByVariable.get(variable.name) ?? null,
        conformity: conformityByVariable.get(variable.name) ?? null,
        precedent: precedentByVariable.get(variable.name) ?? null,
      };
    })
    .sort(
      (a, b) =>
        RELATION_ORDER[a.leadingRelation] - RELATION_ORDER[b.leadingRelation] ||
        attributeLabel(a.variable.name).localeCompare(attributeLabel(b.variable.name)),
    );

  const normalizedQuery = query.trim().toLowerCase();
  const visibleRows = rows.filter((row) => {
    const matchesSearch =
      !normalizedQuery ||
      attributeLabel(row.variable.name).toLowerCase().includes(normalizedQuery) ||
      row.variable.description.toLowerCase().includes(normalizedQuery);
    const matchesRelation =
      relationFilter === "all" ||
      row.matches.some((match) => match.relation === relationFilter);
    return matchesSearch && matchesRelation;
  });

  return (
    <div className="flex flex-col gap-4">
      <CollapsibleCard
        title={`${variables.length} fields`}
        subtitle={`${distinctSourceCount(result).toLocaleString()} sources · ${
          result.stats?.insights ?? 0
        } insights`}
        contentClassName="p-0"
        trailing={
          <>
            <Button variant="ghost" size="sm" onClick={onNewAnalysis}>New analysis</Button>
            <DownloadButton
              filename="scout-result.json"
              data={packScoutResult(result)}
              format="json"
              label="Download JSON"
            />
          </>
        }
      >
        <div>
          <div className="flex flex-col gap-2 border-b border-border/80 bg-muted/10 px-5 py-3 sm:flex-row sm:items-center sm:px-6">
            <label className="relative min-w-0 flex-1 sm:max-w-xs">
              <span className="sr-only">Search fields</span>
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
              <input
                type="search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Find a field…"
                className="h-8 w-full rounded-md border border-input bg-card pl-8 pr-3 text-xs outline-none transition-colors placeholder:text-muted-foreground focus:border-foreground/30 focus:ring-2 focus:ring-ring/10"
              />
            </label>
            <Select
              value={relationFilter}
              onValueChange={(value) => setRelationFilter(value as "all" | Match["relation"])}
            >
              <SelectTrigger className="h-8 w-full bg-card sm:w-40">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All relations</SelectItem>
                <SelectItem value="contradicts">Contradicts</SelectItem>
                <SelectItem value="extends">Extends</SelectItem>
                <SelectItem value="confirms">Confirms</SelectItem>
                <SelectItem value="unrelated">Unrelated</SelectItem>
              </SelectContent>
            </Select>
            <span className="ml-auto text-[11px] tabular-nums text-muted-foreground">
              {visibleRows.length} of {rows.length}
            </span>
          </div>
          {visibleRows.map((row) => (
            <FieldRow
              key={row.variable.name}
              name={row.variable.name}
              description={row.variable.description}
              matches={row.matches}
              assessment={row.assessment}
              conformity={row.conformity}
              precedent={row.precedent}
            />
          ))}
          {visibleRows.length === 0 && (
            <p className="px-6 py-10 text-center text-sm text-muted-foreground">
              No fields match this view.
            </p>
          )}
        </div>
      </CollapsibleCard>
    </div>
  );
}

function FieldRow({
  name,
  description,
  matches,
  assessment,
  conformity,
  precedent,
}: {
  name: string;
  description: string;
  matches: Match[];
  assessment: EvidenceAssessment | null;
  conformity: Conformity | null;
  precedent: PrecedentSignal | null;
}) {
  const evidenceMeta = assessment ? EVIDENCE_META[assessment.strength] : null;
  const precedentMeta = precedent ? PRECEDENT_META[precedent.precedent] : null;
  const counts = relationCounts(matches);
  return (
    <details className="group/field border-b border-border/80 last:border-b-0">
      <summary className="flex cursor-pointer items-start justify-between gap-4 px-5 py-4 transition-colors hover:bg-muted/25 sm:px-6 [&::-webkit-details-marker]:hidden">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2">
            <h3 className="text-sm font-semibold text-foreground">{attributeLabel(name)}</h3>
          </div>
          <p className="mt-1 line-clamp-1 text-xs leading-relaxed text-muted-foreground">
            {description}
          </p>
          <div className="mt-2.5 grid gap-x-6 gap-y-1.5 sm:grid-cols-2 xl:grid-cols-[minmax(0,1.7fr)_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)]">
            <SignalSummary label="Match relations" value={relationSummary(counts)} />
            <SignalSummary
              label="Evidence"
              value={assessment && evidenceMeta ? evidenceMeta.label : "—"}
              detail={assessment ? countLabel(assessment.supporting_findings.length, "source") : undefined}
              dot={assessment && evidenceMeta ? evidenceMeta.dot : undefined}
            />
            <SignalSummary
              label="Precedent"
              value={precedent && precedentMeta ? precedentMeta.label : "—"}
              detail={precedent ? countLabel(precedent.supporting_findings.length, "source") : undefined}
              dot={precedent && precedentMeta ? precedentMeta.dot : undefined}
            />
            <SignalSummary
              label="Conformity"
              value={conformity ? `${Math.round(conformity.conformity * 100)}%` : "—"}
              detail={conformity ? countLabel(conformity.measurements.length, "measurement") : undefined}
              dot={conformity ? CONFORMITY_DOT : undefined}
            />
          </div>
        </div>
        <ChevronDown className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground transition-transform group-open/field:rotate-180" />
      </summary>

      <div className="space-y-3 border-t border-border/70 bg-muted/15 px-5 py-5 sm:px-6">
        {assessment?.doc_target && (
          <div className="rounded-lg border border-border/80 bg-card px-4 py-3.5">
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
    <section className="rounded-lg border border-border/80 bg-card p-4">
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
                    className="min-w-0 flex-1 truncate hover:text-foreground hover:underline"
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
    <section className="rounded-lg border border-border/80 bg-card p-4">
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
    <section className="rounded-lg border border-border/80 bg-card p-4">
      <div className="flex items-center justify-between gap-2">
        <SectionLabel>Precedent · AI judgment</SectionLabel>
        <SignalChip dot={precedentMeta.dot}>{precedentMeta.label}</SignalChip>
      </div>
      <p className="mt-0.5 text-[11px] text-muted-foreground/80">
        Has this target/approach been tried before? Separates a genuinely{" "}
        <span className="text-foreground">novel</span> target (white space — expected for a TPP)
        from a <span className="text-foreground">tried &amp; failed</span> one (attempted before,
        didn&apos;t pan out). It reads disconfirming evidence too, so low evidence isn&apos;t
        mistaken for a gap.
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
          <li key={index} className="rounded-lg border border-border/80 bg-card p-4">
            <SignalChip dot={RELATION_DOT[match.relation]}>{attributeLabel(match.relation)}</SignalChip>
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
