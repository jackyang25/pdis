"use client";

import { useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { AlertTriangle, ChevronDown, Search } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { RunPanel } from "@/components/run-panel";
import { ConfigurationFields } from "@/components/configuration-fields";
import { HeaderGuard } from "@/components/header-guard";
import { EmptyState } from "@/components/empty-state";
import { CollapsibleCard } from "@/components/collapsible-card";
import { DownloadButton } from "@/components/download-button";
import {
  recalibrateScout,
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
import { ComparatorDistributionPlot } from "@/components/comparator-distribution-plot";

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
  { key: "targets", label: "Binding document fields" },
  { key: "quantitative_targets", label: "Structuring measurable targets" },
  { key: "queries", label: "Extracting queries" },
  { key: "search", label: "Searching evidence sources" },
  { key: "insights", label: "Extracting insights" },
  { key: "classify", label: "Detecting drift" },
  { key: "evidence", label: "Assessing evidence grounding" },
  { key: "conformity", label: "Calibrating quantitative assumptions" },
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

function formatOrdinal(value: number): string {
  const remainder = value % 100;
  if (remainder >= 11 && remainder <= 13) return `${value}th`;
  if (value % 10 === 1) return `${value}st`;
  if (value % 10 === 2) return `${value}nd`;
  if (value % 10 === 3) return `${value}rd`;
  return `${value}th`;
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

  async function handleRecalibrate() {
    if (!result || busy) return;
    setBusy(true);
    setError(null);
    setStage("conformity");
    setProgress(null);
    try {
      const recalibrated = await recalibrateScout(result, (s, p) => {
        setStage(s);
        setProgress(p ?? null);
      });
      setResult({ ...result, conformity: recalibrated.conformity });
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
      setStage(null);
      setProgress(null);
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
          configuration={<ConfigurationFields />}
          accept=".docx,.pdf,.pptx"
          busy={busy}
          onRun={handleRun}
          steps={SCOUT_STEPS}
          currentStage={stage}
          progress={progress}
          runDisabled={!ready}
          hint={ready ? undefined : "Complete the configuration to run."}
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
      {result && (
        <FieldGrid
          result={result}
          onNewAnalysis={() => setShowRunPanel(true)}
          onRecalibrate={handleRecalibrate}
          recalibrating={busy && stage === "conformity"}
        />
      )}
      {result && <Ask resultType="scout" result={result} />}
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

function FieldGrid({
  result,
  onNewAnalysis,
  onRecalibrate,
  recalibrating,
}: {
  result: ScoutResponse;
  onNewAnalysis: () => void;
  onRecalibrate: () => void;
  recalibrating: boolean;
}) {
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
  const conformityByVariable = new Map<string, Conformity[]>();
  for (const score of result.conformity ?? []) {
    const scores = conformityByVariable.get(score.attribute_ref) ?? [];
    scores.push(score);
    conformityByVariable.set(score.attribute_ref, scores);
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
        conformities: conformityByVariable.get(variable.name) ?? [],
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
            <Button variant="ghost" size="sm" onClick={onRecalibrate} disabled={recalibrating}>
              {recalibrating ? "Recalculating…" : "Recalculate metrics"}
            </Button>
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
                conformities={row.conformities}
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
  conformities,
  precedent,
}: {
  name: string;
  description: string;
  matches: Match[];
  assessment: EvidenceAssessment | null;
  conformities: Conformity[];
  precedent: PrecedentSignal | null;
}) {
  const evidenceMeta = assessment ? EVIDENCE_META[assessment.strength] : null;
  const precedentMeta = precedent ? precedentView(precedent) : null;
  const counts = relationCounts(matches);
  const verifiedConformities = conformities.filter(
    (score) => score.calibration_status !== "legacy_unverified",
  );
  const hasLegacyConformity = conformities.some(
    (score) => score.calibration_status === "legacy_unverified",
  );
  const comparatorCount = verifiedConformities.reduce(
    (total, score) => total + score.benchmark_count,
    0,
  );
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
              label="Evidence · Quantitative calibration"
              value={hasLegacyConformity
                ? "Rerun required"
                : verifiedConformities.length > 0
                  ? countLabel(verifiedConformities.length, "numeric target")
                  : "Not calculated"}
              detail={hasLegacyConformity
                ? "unverified legacy result"
                : verifiedConformities.length > 0
                  ? countLabel(comparatorCount, "validated comparator")
                  : "no validated numeric target"}
              dot={conformities.length > 0 ? TARGET_ALIGNMENT_DOT : undefined}
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
        {conformities.length > 0 && (
          <div className="space-y-3">
            {conformities.map((conformity) => (
              <ConformityBlock
                key={conformity.target_id}
                conformity={conformity}
                matches={matches}
              />
            ))}
          </div>
        )}
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
    <details className="group/trace relative shrink-0">
      <summary
        className="cursor-pointer list-none whitespace-nowrap rounded-md px-1.5 py-1 text-[10px] font-medium text-muted-foreground/70 transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/20 [&::-webkit-details-marker]:hidden"
        title="Show source document blocks"
      >
        Trace · {blockIds.length} {blockIds.length === 1 ? "block" : "blocks"}
      </summary>
      <div className="absolute right-0 top-full z-30 mt-1.5 w-[min(22rem,calc(100vw-3rem))] rounded-md border border-border bg-popover p-2.5 shadow-lg">
        <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
          Source document blocks
        </p>
        <ul className="mt-1.5 max-h-44 space-y-1 overflow-y-auto pr-1">
          {blockIds.map((blockId) => (
            <li
              key={blockId}
              className="break-all rounded bg-muted/50 px-2 py-1 font-mono text-[10px] leading-relaxed text-foreground/80"
            >
              {blockId}
            </li>
          ))}
        </ul>
      </div>
    </details>
  );
}

function ConformityBlock({ conformity, matches }: { conformity: Conformity; matches: Match[] }) {
  const targetLabel =
    conformity.target_label ||
    `${conformity.comparator} ${conformity.target_value}${conformity.unit}`;
  const formatBenchmark = (value: number | null) =>
    value == null ? "—" : `${value.toLocaleString(undefined, { maximumFractionDigits: 3 })}${conformity.unit}`;
  const ambition = conformity.ambition_percentile == null
    ? "—"
    : `${formatOrdinal(Math.round(conformity.ambition_percentile * 100))} percentile`;
  const coverageLabel = {
    insufficient: "Insufficient basis",
    limited: "Limited basis",
    sufficient: "Broader verified basis",
    legacy_unverified: "Legacy result · unverified",
  }[conformity.calibration_status];
  const targetRoleLabel = {
    threshold: "Threshold",
    optimal: "Optimal",
    other: "Other target",
  }[conformity.target_role];

  if (conformity.calibration_status === "legacy_unverified") {
    return (
      <section className="rounded-lg border border-border/80 bg-card p-4">
        <SectionLabel>Evidence · quantitative calibration</SectionLabel>
        <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
          This imported result predates exact-quote and claim-comparability validation.
          Rerun Scout before using its numeric comparison for a decision.
        </p>
      </section>
    );
  }

  return (
    <section className="rounded-lg border border-border/80 bg-card p-4">
      <div className="flex items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <SectionLabel>Evidence · quantitative calibration · verified spans + calculated</SectionLabel>
          <span className="rounded-full border border-border bg-muted/40 px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
            {targetRoleLabel}
          </span>
        </div>
        <BlockTrace blockIds={conformity.doc_block_ids} />
      </div>
      <p className="mt-0.5 text-[11px] text-muted-foreground/80">
        Exact document and source passages are validated before claim-compatible,
        deduplicated comparators enter these descriptive statistics.
      </p>
      <p className="mt-1 text-[11px] text-muted-foreground">
        Target <span className="text-foreground">{targetLabel}</span>
      </p>
      <blockquote className="mt-2 border-l-2 border-border pl-3 text-xs leading-relaxed text-foreground">
        {conformity.target_quote}
      </blockquote>

      <dl className="mt-3 grid grid-cols-2 overflow-hidden rounded-md border border-border/70 sm:grid-cols-3">
        <StatCell label="External median" value={formatBenchmark(conformity.benchmark_median)} />
        <StatCell label="Middle 50%" value={`${formatBenchmark(conformity.benchmark_lower_quartile)}–${formatBenchmark(conformity.benchmark_upper_quartile)}`} />
        <StatCell label="Observed range" value={`${formatBenchmark(conformity.benchmark_minimum)}–${formatBenchmark(conformity.benchmark_maximum)}`} />
        <StatCell label="Mean · observed SD" value={`${formatBenchmark(conformity.benchmark_mean)} · ${formatBenchmark(conformity.benchmark_standard_deviation)}`} />
        <StatCell label="Target ambition" value={ambition} />
        <StatCell label="Evidence basis" value={`${conformity.benchmark_count} comparator${conformity.benchmark_count === 1 ? "" : "s"}`} detail={coverageLabel} />
      </dl>
      <p className="mt-1.5 text-[10px] leading-relaxed text-muted-foreground/70">
        Range, standard deviation, and percentile describe this selected comparator cohort only.
        They are not population uncertainty or likelihood of success.
      </p>

      {(conformity.benchmark_count > 0 || conformity.excluded_measurements.length > 0) && (
        <ComparatorDistributionPlot conformity={conformity} />
      )}

      {conformity.benchmark_count > 0 && (
        <p className="mt-1.5 text-[10px] text-muted-foreground/70">
          The observed share is a literal count within the validated cohort, not a probability or confidence interval.
        </p>
      )}

      <div className="mt-3">
        <SignalChip dot={TARGET_ALIGNMENT_DOT}>{conformity.verdict}</SignalChip>
      </div>

      {conformity.measurements.length > 0 && (
        <div className="mt-3">
          <SectionLabel>Included comparator cohort · {conformity.measurements.length}</SectionLabel>
          <ul className="mt-1 divide-y divide-border/70">
            {conformity.measurements.map((measurement, index) => {
              const sourceInsight = matches.find(
                (match) => match.insight.id === measurement.insight_id,
              )?.insight;
              const evidenceLabels = [
                EVIDENCE_FORM_LABELS[measurement.evidence_form] ?? measurement.evidence_form,
                PHASE_LABELS[measurement.development_phase],
                SOURCE_RECORD_LABELS[measurement.source_record_type],
              ].filter(Boolean);
              return (
                <li key={`${measurement.url}-${index}`} className="py-2 text-xs text-muted-foreground first:pt-1">
                  <div className="flex items-baseline gap-2">
                    <a href={measurement.url} target="_blank" rel="noreferrer" className="min-w-0 flex-1 truncate hover:text-foreground hover:underline">
                      {evidenceLabels.join(" · ")}
                    </a>
                    <span className="shrink-0 text-[11px] text-muted-foreground/60">
                      {measurement.value}{measurement.unit} · {measurement.age_months != null ? `${Math.round(measurement.age_months)}mo` : "date unknown"}
                    </span>
                  </div>
                  <blockquote className="mt-1 border-l border-border pl-2 text-[11px] leading-relaxed text-foreground/80">
                    {measurement.source_quote}
                  </blockquote>
                  <p className="mt-1 text-[10px] text-muted-foreground/70">
                    {measurement.inclusion_reason} Identity: {measurement.source_identity_status.replace("_", " ")}.
                  </p>
                  <details className="mt-1 text-[10px] text-muted-foreground/70">
                    <summary className="cursor-pointer">Why this comparator qualifies</summary>
                    <ul className="mt-1 space-y-0.5 pl-3">
                      {Object.entries(measurement.comparability).map(([axis, relation]) => {
                        const evidence = measurement.axis_evidence?.[axis];
                        const cited = Boolean(
                          evidence?.target_span_ids?.length && evidence?.source_span_ids?.length,
                        );
                        return (
                          <li key={axis}>
                            {axis.replace("_", " ")}: {relation.replace("_", " ")}
                            {measurement.comparability_reasons[axis] ? ` — ${measurement.comparability_reasons[axis]}` : ""}
                            {cited ? " · spans verified" : ""}
                          </li>
                        );
                      })}
                    </ul>
                  </details>
                  {sourceInsight && <p className="mt-0.5 line-clamp-1 text-[10px] text-muted-foreground/60">Insight: {sourceInsight.statement}</p>}
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {conformity.excluded_measurements.length > 0 && (
        <details className="mt-3 border-t border-border/70 pt-3">
          <summary className="cursor-pointer text-[11px] font-medium text-muted-foreground">
            {conformity.excluded_measurements.length} grounded candidate{conformity.excluded_measurements.length === 1 ? "" : "s"} excluded
          </summary>
          <ul className="mt-2 space-y-2">
            {conformity.excluded_measurements.map((measurement, index) => (
              <li key={`${measurement.url}-excluded-${index}`} className="rounded-md bg-muted/40 px-3 py-2 text-[11px] text-muted-foreground">
                <div className="flex justify-between gap-3">
                  <a href={measurement.url} target="_blank" rel="noreferrer" className="truncate hover:text-foreground hover:underline">
                    {measurement.source_record_id}
                  </a>
                  <span>{measurement.value}{measurement.unit}</span>
                </div>
                <p className="mt-1 text-foreground/75">“{measurement.source_quote}”</p>
                <p className="mt-1">{measurement.exclusion_reasons.join(" · ")}</p>
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}

function StatCell({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return (
    <div className="border-b border-r border-border/70 px-3 py-2.5 last:border-r-0 sm:[&:nth-last-child(-n+3)]:border-b-0">
      <dt className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">{label}</dt>
      <dd className="mt-0.5 text-xs font-medium text-foreground">{value}</dd>
      {detail && <dd className="text-[10px] text-muted-foreground">{detail}</dd>}
    </div>
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
