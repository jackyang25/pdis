"use client";

import { useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { AlertTriangle, ChevronDown, Search } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { RunPanel } from "@/components/run-panel";
import { HeaderGuard } from "@/components/header-guard";
import { EmptyState } from "@/components/empty-state";
import { CollapsibleCard } from "@/components/collapsible-card";
import { DownloadButton } from "@/components/download-button";
import {
  runScout,
  type Conformity,
  type DevelopmentProgram,
  type EvidenceAssessment,
  type Finding,
  type Header,
  type Match,
  type ScoutResponse,
  type SafetySignal,
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
import { displayAttributeLabel } from "@/lib/scout-evidence-map";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  ScoutSignalHelp,
  ScoutSignalLabel,
  type ScoutSignalTopic,
} from "@/components/scout-signal-help";
import { SourceAttributions } from "@/components/source-attributions";

const ScoutEvidenceMap = dynamic(
  () =>
    import("@/components/scout-evidence-map").then(
      (module) => module.ScoutEvidenceMap,
    ),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-[560px] items-center justify-center text-xs text-muted-foreground">
        Preparing evidence map…
      </div>
    ),
  },
);

const SCOUT_STEPS = [
  { key: "parse", label: "Parsing documents" },
  { key: "context", label: "Validating document context" },
  { key: "targets", label: "Resolving document targets" },
  { key: "queries", label: "Extracting queries" },
  { key: "search", label: "Searching evidence sources" },
  { key: "insights", label: "Extracting insights" },
  { key: "classify", label: "Detecting drift" },
  { key: "evidence", label: "Assessing evidence grounding" },
  { key: "conformity", label: "Calculating evidence alignment" },
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

const RELATION_LABEL: Record<Match["relation"], string> = {
  contradicts: "Conflicts",
  extends: "Adds context",
  confirms: "Supports",
  unrelated: "Unrelated",
};

const EVIDENCE_FORM_LABELS: Record<string, string> = {
  evidence_synthesis: "Evidence synthesis",
  randomized_trial: "Randomized trial",
  nonrandomized_trial: "Nonrandomized trial",
  observational_study: "Observational study",
  implementation_evidence: "Implementation evidence",
  regulatory_review: "Regulatory review",
  registry_record: "Registry record",
  other: "Other evidence",
};

const PHASE_LABELS: Record<string, string> = {
  phase_1: "Phase 1",
  phase_2: "Phase 2",
  phase_3: "Phase 3",
  phase_4: "Phase 4",
  not_applicable: "",
  unknown: "",
};

const SOURCE_RECORD_LABELS: Record<string, string> = {
  peer_reviewed: "Peer reviewed",
  preprint: "Preprint",
  regulatory: "Regulatory",
  registry: "Registry",
  company_report: "Company report",
  unknown: "",
};

// Target alignment is a position (target vs current evidence), NOT a good/bad grade:
// a low score often reflects an intentional stretch target, not a failure. So
// its chip uses a single neutral tone rather than green/red, to avoid being
// read as a pass/fail score.
const TARGET_ALIGNMENT_DOT = "bg-slate-400";

const PRECEDENT_META: Record<PrecedentSignal["precedent"], { label: string; dot: string }> = {
  direct: { label: "Direct", dot: NEUTRAL_DOT },
  adjacent: { label: "Adjacent", dot: NEUTRAL_DOT },
  none: { label: "None found", dot: NEUTRAL_DOT },
  unknown: { label: "Unknown", dot: NEUTRAL_DOT },
};

const OUTCOME_META = {
  favorable: { label: "Favorable", dot: "bg-emerald-500" },
  mixed: { label: "Mixed", dot: "bg-amber-400" },
  unfavorable: { label: "Unfavorable", dot: "bg-red-500" },
  unknown: { label: "Outcome unknown", dot: NEUTRAL_DOT },
} as const;

function precedentView(signal: PrecedentSignal) {
  const coverage = PRECEDENT_META[signal.precedent].label;
  const outcome = OUTCOME_META[signal.outcome];
  return { coverage, outcome: outcome.label, dot: outcome.dot };
}

function formatDate(iso: string | null): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (isNaN(d.getTime())) return null;
  return d.toLocaleDateString("en-US", { year: "numeric", month: "short" });
}

function sourceDisplayLabel(source: string, labels?: Record<string, string>): string {
  return (
    labels?.[source] ??
    source
      .replace(/[_-]+/g, " ")
      .replace(/\b\w/g, (character) => character.toUpperCase())
  );
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
  helpTopic,
}: {
  label: string;
  value: string;
  detail?: string;
  dot?: string;
  helpTopic?: ScoutSignalTopic;
}) {
  return (
    <div className="min-w-0">
      <p className="text-[11px] font-medium text-muted-foreground">
        {helpTopic ? (
          <ScoutSignalLabel topic={helpTopic}>{label}</ScoutSignalLabel>
        ) : (
          label
        )}
      </p>
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
    .map((key) => `${RELATION_LABEL[key]} ${counts[key]}`);
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
        const sourceLabels = (f.source_lanes?.length ? f.source_lanes : [f.source]).map(
          (lane) => sourceDisplayLabel(lane, f.source_labels),
        );
        const sourceLabel = Array.from(new Set(sourceLabels)).join(" + ");
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
      <PageHeader title="Scout" description="Pressure-test document targets against live evidence, precedent, and quantitative alignment." />
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
      {result && <ContextValidationNotice result={result} />}
      {result && <FieldGrid result={result} onNewAnalysis={() => setShowRunPanel(true)} />}
      <Ask resultType="scout" result={result} />
      {!result && !busy && !error && (
        <EmptyState message="Upload a document to begin." />
      )}
    </div>
  );
}

function ContextValidationNotice({ result }: { result: ScoutResponse }) {
  const validation = result.context_validation;
  if (!validation || validation.status === "match") return null;

  const message =
    validation.status === "not_checked"
      ? "This imported result predates document-context validation. Re-run it before relying on indication-scoped evidence."
      : validation.status === "mismatch"
        ? `The document appears to concern ${validation.document_indication || "a different indication"}, not ${validation.configured_indication}.`
        : `Scout could not confidently verify that the document concerns ${validation.configured_indication}.`;

  return (
    <div
      role="status"
      className="flex items-start gap-2.5 rounded-lg border border-amber-300/60 bg-amber-50/60 px-3.5 py-3 text-xs text-amber-950"
    >
      <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
      <div className="min-w-0">
        <p className="font-medium">Review document context</p>
        <p className="mt-0.5 leading-relaxed text-amber-950/75">
          {message} {validation.reason}
        </p>
      </div>
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
  for (const program of result.development_landscape ?? [])
    for (const finding of program.supporting_findings ?? []) if (finding.url) urls.add(finding.url);
  for (const signal of result.safety_signals ?? [])
    for (const finding of signal.supporting_findings ?? []) if (finding.url) urls.add(finding.url);
  return urls.size;
}

function resultFindings(result: ScoutResponse): Finding[] {
  return [
    ...(result.matches ?? []).flatMap(
      (match) => match.insight.supporting_findings ?? [],
    ),
    ...(result.assessments ?? []).flatMap(
      (assessment) => assessment.supporting_findings ?? [],
    ),
    ...(result.precedents ?? []).flatMap(
      (precedent) => precedent.supporting_findings ?? [],
    ),
    ...(result.development_landscape ?? []).flatMap(
      (program) => program.supporting_findings ?? [],
    ),
    ...(result.safety_signals ?? []).flatMap(
      (signal) => signal.supporting_findings ?? [],
    ),
  ];
}

function FieldGrid({ result, onNewAnalysis }: { result: ScoutResponse; onNewAnalysis: () => void }) {
  const matches = result.matches ?? [];
  const variables = result.variables ?? [];
  const developmentLandscape = result.development_landscape ?? [];
  const safetySignals = result.safety_signals ?? [];
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
        displayAttributeLabel(a.variable.name).localeCompare(displayAttributeLabel(b.variable.name)),
    );

  const normalizedQuery = query.trim().toLowerCase();
  const visibleRows = rows.filter((row) => {
    const matchesSearch =
      !normalizedQuery ||
      displayAttributeLabel(row.variable.name).toLowerCase().includes(normalizedQuery) ||
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
        <Tabs defaultValue="fields">
          <div className="border-b border-border/80 px-5 pt-3 sm:px-6">
            <TabsList className="border-b-0">
              <TabsTrigger value="fields">Fields</TabsTrigger>
              {developmentLandscape.length > 0 && (
                <TabsTrigger value="landscape">Landscape</TabsTrigger>
              )}
              {safetySignals.length > 0 && (
                <TabsTrigger value="safety">Safety</TabsTrigger>
              )}
              <TabsTrigger value="map">Evidence map</TabsTrigger>
            </TabsList>
          </div>
          <TabsContent value="fields" className="mt-0">
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
                  <SelectItem value="all">All relationships</SelectItem>
                  <SelectItem value="contradicts">Conflicts</SelectItem>
                  <SelectItem value="extends">Adds context</SelectItem>
                  <SelectItem value="confirms">Supports</SelectItem>
                  <SelectItem value="unrelated">Unrelated</SelectItem>
                </SelectContent>
              </Select>
              <div className="flex w-full items-center justify-between gap-3 sm:ml-auto sm:w-auto sm:justify-start">
                <ScoutSignalHelp />
                <span className="text-[11px] tabular-nums text-muted-foreground">
                  {visibleRows.length} of {rows.length}
                </span>
              </div>
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
          </TabsContent>
          {developmentLandscape.length > 0 && (
            <TabsContent value="landscape" className="mt-0">
              <DevelopmentLandscape programs={developmentLandscape} />
            </TabsContent>
          )}
          {safetySignals.length > 0 && (
            <TabsContent value="safety" className="mt-0">
              <SafetySignals signals={safetySignals} />
            </TabsContent>
          )}
          <TabsContent value="map" className="mt-0">
            <ScoutEvidenceMap result={result} />
          </TabsContent>
        </Tabs>
        <SourceAttributions
          findings={resultFindings(result)}
          className="border-t border-border/80 px-5 py-3 sm:px-6"
        />
      </CollapsibleCard>
    </div>
  );
}

function DevelopmentLandscape({ programs }: { programs: DevelopmentProgram[] }) {
  const [query, setQuery] = useState("");
  const normalizedQuery = query.trim().toLowerCase();
  const visible = programs.filter((program) =>
    !normalizedQuery ||
    [program.name, ...program.sponsors, ...program.phases, ...program.statuses]
      .join(" ")
      .toLowerCase()
      .includes(normalizedQuery),
  );
  return (
    <section>
      <div className="flex flex-col gap-2 border-b border-border/80 bg-muted/10 px-5 py-3 sm:flex-row sm:items-center sm:px-6">
        <label className="relative min-w-0 flex-1 sm:max-w-xs">
          <span className="sr-only">Search development programs</span>
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Find a program…"
            className="h-8 w-full rounded-md border border-input bg-card pl-8 pr-3 text-xs outline-none transition-colors placeholder:text-muted-foreground focus:border-foreground/30 focus:ring-2 focus:ring-ring/10"
          />
        </label>
        <p className="text-[11px] text-muted-foreground sm:ml-auto">
          Structured records only · {visible.length} of {programs.length}
        </p>
      </div>
      {visible.map((program) => (
        <details key={program.name} className="group/program border-b border-border/80 last:border-b-0">
          <summary className="flex cursor-pointer items-start gap-4 px-5 py-4 hover:bg-muted/25 sm:px-6 [&::-webkit-details-marker]:hidden">
            <div className="min-w-0 flex-1">
              <h3 className="truncate text-sm font-semibold text-foreground">{program.name}</h3>
              <div className="mt-2 grid gap-x-6 gap-y-1.5 sm:grid-cols-3">
                <SignalSummary label="Sponsor" value={program.sponsors.join(" · ") || "—"} />
                <SignalSummary label="Phase" value={program.phases.join(" · ") || "—"} />
                <SignalSummary label="Status" value={program.statuses.join(" · ") || "—"} />
              </div>
            </div>
            <div className="flex shrink-0 items-center gap-3">
              <span className="text-[11px] text-muted-foreground">
                {countLabel(program.supporting_findings.length, "record")}
              </span>
              <ChevronDown className="h-4 w-4 text-muted-foreground transition-transform group-open/program:rotate-180" />
            </div>
          </summary>
          <div className="border-t border-border/70 bg-muted/15 px-5 py-4 sm:px-6">
            {program.attribute_refs.length > 0 && (
              <p className="text-[11px] text-muted-foreground">
                Retrieved for {program.attribute_refs.map(displayAttributeLabel).join(" · ")}
              </p>
            )}
            <SourceList findings={program.supporting_findings} />
          </div>
        </details>
      ))}
      {visible.length === 0 && (
        <p className="px-6 py-10 text-center text-sm text-muted-foreground">
          No programs match this view.
        </p>
      )}
    </section>
  );
}

const SAFETY_TYPE_LABELS: Record<string, string> = {
  label_warning: "Official label",
  reported_event: "Reported event",
  device_event: "Device report",
  recall: "Recall",
};

function SafetySignals({ signals }: { signals: SafetySignal[] }) {
  const [query, setQuery] = useState("");
  const normalizedQuery = query.trim().toLowerCase();
  const visible = signals.filter((signal) =>
    !normalizedQuery ||
    `${signal.product_name} ${signal.signal} ${signal.detail}`
      .toLowerCase()
      .includes(normalizedQuery),
  );
  return (
    <section>
      <div className="border-b border-border/80 bg-muted/20 px-5 py-3 text-[11px] leading-relaxed text-muted-foreground sm:px-6">
        Safety records are surveillance and labeling signals. Report counts are not incidence estimates and do not establish causation.
      </div>
      <div className="flex items-center gap-3 border-b border-border/80 bg-muted/10 px-5 py-3 sm:px-6">
        <label className="relative min-w-0 flex-1 sm:max-w-xs">
          <span className="sr-only">Search safety signals</span>
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Find a product or signal…"
            className="h-8 w-full rounded-md border border-input bg-card pl-8 pr-3 text-xs outline-none transition-colors placeholder:text-muted-foreground focus:border-foreground/30 focus:ring-2 focus:ring-ring/10"
          />
        </label>
        <span className="ml-auto text-[11px] text-muted-foreground">
          {visible.length} of {signals.length}
        </span>
      </div>
      {visible.map((signal, index) => (
        <details key={`${signal.product_name}-${signal.signal_type}-${signal.signal}-${index}`} className="group/safety border-b border-border/80 last:border-b-0">
          <summary className="flex cursor-pointer items-start gap-4 px-5 py-4 hover:bg-muted/25 sm:px-6 [&::-webkit-details-marker]:hidden">
            <div className="min-w-0 flex-1">
              <p className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                {SAFETY_TYPE_LABELS[signal.signal_type] ?? signal.signal_type}
              </p>
              <h3 className="mt-1 text-sm font-semibold text-foreground">{signal.product_name}</h3>
              <p className="mt-1 line-clamp-1 text-xs text-muted-foreground">{signal.signal}</p>
            </div>
            <div className="flex shrink-0 items-center gap-3">
              {signal.count != null && (
                <span className="text-xs tabular-nums text-muted-foreground">
                  {signal.count.toLocaleString()} reports
                </span>
              )}
              <ChevronDown className="h-4 w-4 text-muted-foreground transition-transform group-open/safety:rotate-180" />
            </div>
          </summary>
          <div className="border-t border-border/70 bg-muted/15 px-5 py-4 sm:px-6">
            {signal.detail && (
              <p className="max-w-4xl text-xs leading-relaxed text-foreground/90">{signal.detail}</p>
            )}
            {signal.qualification && (
              <p className="mt-2 text-[11px] leading-relaxed text-muted-foreground">{signal.qualification}</p>
            )}
            <SourceList findings={signal.supporting_findings} />
          </div>
        </details>
      ))}
    </section>
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
  const precedentMeta = precedent ? precedentView(precedent) : null;
  const counts = relationCounts(matches);
  return (
    <details className="group/field border-b border-border/80 last:border-b-0">
      <summary className="flex cursor-pointer items-start justify-between gap-4 px-5 py-4 transition-colors hover:bg-muted/25 sm:px-6 [&::-webkit-details-marker]:hidden">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2">
            <h3 className="text-sm font-semibold text-foreground">{displayAttributeLabel(name)}</h3>
          </div>
          <p className="mt-1 line-clamp-1 text-xs leading-relaxed text-muted-foreground">
            {description}
          </p>
          <div className="mt-2.5 grid gap-x-6 gap-y-1.5 sm:grid-cols-2 xl:grid-cols-[minmax(0,1.7fr)_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)]">
            <SignalSummary
              label="Evidence relationships"
              value={relationSummary(counts)}
              helpTopic="relationships"
            />
            <SignalSummary
              label="Evidence · Grounding"
              value={assessment && evidenceMeta ? evidenceMeta.label : "—"}
              detail={assessment ? countLabel(assessment.supporting_findings.length, "source") : undefined}
              dot={assessment && evidenceMeta ? evidenceMeta.dot : undefined}
              helpTopic="grounding"
            />
            <SignalSummary
              label="Evidence · Target alignment"
              value={conformity ? `${Math.round(conformity.conformity * 100)}/100` : "—"}
              detail={conformity ? countLabel(conformity.measurements.length, "measurement") : undefined}
              dot={conformity ? TARGET_ALIGNMENT_DOT : undefined}
              helpTopic="alignment"
            />
            <SignalSummary
              label="Precedent"
              value={precedent && precedentMeta ? `${precedentMeta.coverage} · ${precedentMeta.outcome}` : "—"}
              detail={precedent ? countLabel(precedent.supporting_findings.length, "source") : undefined}
              dot={precedent && precedentMeta ? precedentMeta.dot : undefined}
              helpTopic="precedent"
            />
          </div>
        </div>
        <ChevronDown className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground transition-transform group-open/field:rotate-180" />
      </summary>

      <div className="space-y-3 border-t border-border/70 bg-muted/15 px-5 py-5 sm:px-6">
        {assessment?.doc_target && (
          <div className="rounded-lg border border-border/80 bg-card px-4 py-3.5">
            <div className="flex items-center justify-between gap-3">
              <SectionLabel>Document target · AI extracted</SectionLabel>
              <BlockTrace blockIds={assessment.doc_block_ids} />
            </div>
            <p className="mt-1 text-sm leading-relaxed text-foreground">
              {assessment.doc_target}
            </p>
            <p className="mt-1 text-[11px] text-muted-foreground/70">
              Everything below is external evidence assessed against this.
            </p>
          </div>
        )}
        {conformity && <ConformityBlock conformity={conformity} matches={matches} />}
        {assessment && evidenceMeta && (
          <EvidenceBlock assessment={assessment} evidenceMeta={evidenceMeta} matches={matches} />
        )}
        {precedent && precedentMeta && (
          <PrecedentBlock precedent={precedent} precedentMeta={precedentMeta} matches={matches} />
        )}
        <MatchesBlock matches={matches} />
      </div>
    </details>
  );
}

function BlockTrace({ blockIds }: { blockIds?: string[] }) {
  if (!blockIds?.length) return null;
  return (
    <span className="shrink-0 text-[10px] text-muted-foreground/60" title="Source document blocks">
      {blockIds.join(" · ")}
    </span>
  );
}

function ConformityBlock({ conformity, matches }: { conformity: Conformity; matches: Match[] }) {
  const pct = Math.round(conformity.conformity * 100);
  const lowerPct = Math.round(conformity.lower * 100);
  const upperPct = Math.round(conformity.upper * 100);
  const targetLabel =
    conformity.target_label ||
    `${conformity.comparator} ${conformity.target_value}${conformity.unit}`;

  return (
    <section className="rounded-lg border border-border/80 bg-card p-4">
      <div className="flex items-center justify-between gap-3">
        <SectionLabel>Evidence · target alignment · AI extracted + calculated</SectionLabel>
        <BlockTrace blockIds={conformity.doc_block_ids} />
      </div>
      <p className="mt-0.5 text-[11px] text-muted-foreground/80">
        A directional evidence-alignment score weighted by evidence form, development phase,
        source-record type, and recency. It is not a forecast probability or pass/fail grade.
      </p>
      <p className="mt-1 text-[11px] text-muted-foreground">
        Scored vs <span className="text-foreground">{targetLabel}</span>
      </p>

      <div className="mt-3">
        <div className="mb-1 flex items-baseline justify-between gap-2">
          <span className="text-sm font-semibold text-foreground">{pct}/100 alignment</span>
          <span className="text-xs text-muted-foreground">
            range {lowerPct}–{upperPct}/100
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
        <SignalChip dot={TARGET_ALIGNMENT_DOT}>{conformity.verdict}</SignalChip>
      </div>

      {conformity.measurements.length > 0 && (
        <div className="mt-3">
          <SectionLabel>
            {conformity.measurements.length} source
            {conformity.measurements.length === 1 ? "" : "s"} combined · weighted by quality &amp; recency
          </SectionLabel>
          <ul className="mt-1 space-y-1">
            {conformity.measurements.map((m, index) => {
              const sourceInsight = matches.find((match) => match.insight.id === m.insight_id)?.insight;
              const evidenceLabels = [
                EVIDENCE_FORM_LABELS[m.evidence_form] ?? m.evidence_form,
                PHASE_LABELS[m.development_phase],
                SOURCE_RECORD_LABELS[m.source_record_type],
              ].filter(Boolean);
              const evidenceLabel = evidenceLabels.join(" · ");
              return (
                <li key={`${m.url}-${index}`} className="text-xs text-muted-foreground">
                  <div className="flex items-baseline gap-2">
                    {m.url ? (
                      <a href={m.url} target="_blank" rel="noreferrer" className="min-w-0 flex-1 truncate hover:text-foreground hover:underline">
                        {evidenceLabel}
                      </a>
                    ) : (
                      <span className="min-w-0 flex-1 truncate">{evidenceLabel}</span>
                    )}
                    <span className="shrink-0 text-[11px] text-muted-foreground/60">
                      {m.value}{m.unit ?? conformity.unit} · {m.age_months != null ? `${Math.round(m.age_months)}mo` : "date unknown"} · wt {m.weight.toFixed(2)}
                    </span>
                  </div>
                  {sourceInsight && <p className="mt-0.5 line-clamp-1 text-[11px] text-muted-foreground/70">{sourceInsight.statement}</p>}
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </section>
  );
}

function EvidenceBlock({
  assessment,
  evidenceMeta,
  matches,
}: {
  assessment: EvidenceAssessment;
  evidenceMeta: { label: string; dot: string };
  matches: Match[];
}) {
  return (
    <section className="rounded-lg border border-border/80 bg-card p-4">
      <div className="flex items-center justify-between gap-2">
        <SectionLabel>Evidence · grounding · AI assessment</SectionLabel>
        <SignalChip dot={evidenceMeta.dot}>{evidenceMeta.label}</SignalChip>
      </div>
      <p className="mt-0.5 text-[11px] text-muted-foreground/80">
        How well-grounded and justified your target is
      </p>
      {assessment.reason && (
        <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{assessment.reason}</p>
      )}
      <SupportingInsights
        insightIds={assessment.supporting_insight_ids}
        matches={matches}
        fallback={assessment.supporting_findings}
      />
    </section>
  );
}

function PrecedentBlock({
  precedent,
  precedentMeta,
  matches,
}: {
  precedent: PrecedentSignal;
  precedentMeta: { coverage: string; outcome: string; dot: string };
  matches: Match[];
}) {
  const hasAxisLineage = Boolean(
    precedent.coverage_insight_ids?.length || precedent.outcome_insight_ids?.length,
  );
  return (
    <section className="rounded-lg border border-border/80 bg-card p-4">
      <div className="flex items-center justify-between gap-2">
        <SectionLabel>Precedent · AI judgment</SectionLabel>
        <div className="flex items-center gap-3">
          <SignalChip dot={NEUTRAL_DOT}>{precedentMeta.coverage}</SignalChip>
          <SignalChip dot={precedentMeta.dot}>{precedentMeta.outcome}</SignalChip>
        </div>
      </div>
      <p className="mt-0.5 text-[11px] text-muted-foreground/80">
        Coverage says whether prior work is direct, adjacent, absent, or unknown. Outcome
        separately says whether that prior work was favorable, mixed, or unfavorable.
      </p>
      {precedent.reason && (
        <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{precedent.reason}</p>
      )}
      {hasAxisLineage ? (
        <>
          <SupportingInsights
            label="Coverage evidence"
            insightIds={precedent.coverage_insight_ids}
            matches={matches}
            fallback={[]}
          />
          <SupportingInsights
            label="Outcome evidence"
            insightIds={precedent.outcome_insight_ids}
            matches={matches}
            fallback={[]}
          />
        </>
      ) : (
        <SupportingInsights
          label="Supporting evidence"
          insightIds={precedent.supporting_insight_ids}
          matches={matches}
          fallback={precedent.supporting_findings}
        />
      )}
    </section>
  );
}

function SupportingInsights({
  label,
  insightIds,
  matches,
  fallback,
}: {
  label?: string;
  insightIds?: string[];
  matches: Match[];
  fallback: Finding[];
}) {
  const selected = insightIds?.length
    ? matches.filter((match) => match.insight.id && insightIds.includes(match.insight.id))
    : [];
  if (!selected.length) {
    if (!fallback.length) return null;
    return (
      <div className="mt-3 border-t border-border/70 pt-3">
        {label && <SectionLabel>{label}</SectionLabel>}
        <SourceList findings={fallback} />
      </div>
    );
  }
  return (
    <div className="mt-3 space-y-3 border-t border-border/70 pt-3">
      {label && <SectionLabel>{label}</SectionLabel>}
      {selected.map((match) => (
        <div key={match.insight.id}>
          <p className="text-xs leading-relaxed text-foreground/90">{match.insight.statement}</p>
          <SourceList findings={match.insight.supporting_findings} />
        </div>
      ))}
    </div>
  );
}

function MatchesBlock({ matches }: { matches: Match[] }) {
  if (matches.length === 0) {
    return <p className="text-sm text-muted-foreground">No matches for this variable.</p>;
  }
  return (
    <section>
      <SectionLabel>Evidence relationships · AI judgment · {relationSummary(relationCounts(matches))}</SectionLabel>
      <ul className="mt-2 space-y-3">
        {matches.map((match, index) => (
          <li key={index} className="rounded-lg border border-border/80 bg-card p-4">
            <SignalChip dot={RELATION_DOT[match.relation]}>{RELATION_LABEL[match.relation]}</SignalChip>
            <p className="mt-3 text-sm font-medium leading-relaxed text-foreground">
              {match.insight.statement}
            </p>
            {match.reason && (
              <p className="mt-2 border-l-2 border-border pl-3 text-xs leading-relaxed text-muted-foreground">
                {match.reason}
              </p>
            )}
            <BlockTrace blockIds={match.doc_block_ids} />
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
