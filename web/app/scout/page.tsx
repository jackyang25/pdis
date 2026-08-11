"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import dynamic from "next/dynamic";
import {
  AlertTriangle,
  CalendarRange,
  ChevronDown,
  CircleHelp,
  Search,
} from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { ErrorMessage } from "@/components/ui/error-message";
import { RunPanel } from "@/components/run-panel";
import { RunHistory } from "@/components/run-history";
import {
  ContextFields,
  SourceTypeField,
} from "@/components/configuration-fields";
import {
  ConfigDateInput,
  ConfigField,
  ConfigFieldGrid,
  ConfigurationShell,
} from "@/components/ui/config-field";
import { useHeaderStore } from "@/lib/store";
import { HeaderGuard } from "@/components/header-guard";
import { EmptyState } from "@/components/empty-state";
import { CollapsibleCard } from "@/components/collapsible-card";
import { FinalResultActions } from "@/components/final-result-actions";
import {
  continueScout,
  runScout,
  type Conformity,
  type DevelopmentProgram,
  type EvidenceAssessment,
  type Finding,
  type Header,
  type Match,
  type Measurement,
  type NumericExpression,
  type QuantitativeSemanticProfile,
  type QuantitativeTarget,
  type SemanticSlot,
  type ScoutResponse,
  type SafetyObservation,
  type SourceRole,
  type TargetRelationship,
  type PrecedentSignal,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  IMPORT_LIMIT_MESSAGE,
  MAX_RESULTS_PER_TOOL,
  RESULT_LIMIT_MESSAGE,
  useScoutSession,
} from "@/lib/session";
import { usePriorityDigest } from "@/lib/priority-digest";
import { toolAuthority } from "@/lib/tools";
import { useScoutReviewSession } from "@/lib/scout-review-session";
import {
  isScoutResultFinal,
  packScoutResult,
  runLabel,
  pendingQuantitativeReviewCount,
  splitResultContext,
  scoutResultFilename,
  unpackScoutResult,
  readResultIdentity,
} from "@/lib/result-file";
import { displayAttributeLabel, sourceDisplayLabel } from "@/lib/scout-labels";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ScoutDocumentTrace } from "@/components/scout-document-trace";
import {
  ScoutSignalHelp,
  ScoutSignalLabel,
  type ScoutSignalTopic,
} from "@/components/scout-signal-help";
import { SourceAttributions } from "@/components/source-attributions";
import { ComparatorDistributionPlot } from "@/components/comparator-distribution-plot";
import { Skeleton } from "@/components/ui/skeleton";
import { RELATION_ORDER, sortMatchesForReading } from "@/lib/scout-match-order";
import {
  SCOUT_EMPTY_MESSAGE,
  SCOUT_ORDER_NOTE,
  selectScoutPriorities,
} from "@/lib/scout-priorities";
import { PriorityPanel } from "@/components/ui/priority-panel";
import { cn } from "@/lib/utils";
import { DISCLOSURE_MOTION, SURFACE_ENTRY_MOTION } from "@/lib/motion";
import {
  applyEvidenceReviewRecommendations,
  evidenceReviewRecommendationSummary,
  reviewQuantitativeCandidateGroup,
} from "@/lib/quantitative-review";
import {
  DocumentSourceProvider,
  DocumentSourceTrace,
  type DocumentSpan,
} from "@/components/document-source-trace";
import {
  filterProjectionsByRelationship,
  isContextualRelationship,
  relationshipLabel,
  sourceRoleLabel,
  type ProjectionRelationshipFilter,
} from "@/lib/scout-projection-roles";
import {
  groupSafetyObservations,
  safetyObservationCountLabel,
  safetyRecordTypeLabel,
  safetySourceSystemLabel,
} from "@/lib/scout-safety-observations";

const ScoutEvidenceMap = dynamic(
  () =>
    import("@/components/scout-evidence-map").then(
      (module) => module.ScoutEvidenceMap,
    ),
  {
    ssr: false,
    loading: () => (
      <div className="h-[560px] space-y-3 p-5" role="status" aria-label="Preparing evidence map">
        <Skeleton className="h-4 w-48" />
        <Skeleton className="h-[440px]" />
        <Skeleton className="h-3 w-64" />
      </div>
    ),
  },
);

const SCOUT_STEPS = [
  { key: "parse", label: "Parsing documents" },
  { key: "context", label: "Validating document context" },
  { key: "targets", label: "Binding document fields" },
  { key: "quantitative_targets", label: "Structuring measurable targets" },
  { key: "target_review", label: "Prefilling target review" },
  { key: "queries", label: "Extracting queries" },
  { key: "search", label: "Searching evidence sources" },
  { key: "insights", label: "Extracting insights" },
  { key: "classify", label: "Detecting drift" },
  { key: "evidence", label: "Assessing evidence grounding" },
  { key: "conformity", label: "Calibrating quantitative assumptions" },
  { key: "evidence_review", label: "Prefilling evidence review" },
  { key: "precedent", label: "Checking precedent" },
];

const SOURCE_LIST_LIMIT = 5;


// Tone tokens are reserved for direct signal values, never derived UI grades.
const NEUTRAL_DOT = "bg-muted-foreground/40";

const EVIDENCE_META: Record<EvidenceAssessment["strength"], { label: string; dot: string }> = {
  well_grounded: { label: "Well grounded", dot: "bg-emerald-500" },
  partial: { label: "Partial", dot: "bg-blue-500" },
  thin: { label: "Thin", dot: "bg-amber-400" },
  unsupported: { label: "Unsupported", dot: "bg-[hsl(var(--tone-danger))]" },
  unknown: { label: "Unknown", dot: NEUTRAL_DOT },
};

const RELATION_DOT: Record<Match["relation"], string> = {
  contradicts: "bg-[hsl(var(--tone-danger))]",
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

// Target alignment is a position (target vs current evidence), NOT a good/bad grade:
// a low score often reflects an intentional stretch target, not a failure. So
// its chip uses a single neutral tone rather than green/red, to avoid being
// read as a pass/fail score.
const TARGET_ALIGNMENT_DOT = "bg-slate-400";

function formatNumericExpression(expression: NumericExpression): string {
  const unit = expression.unit ?? "";
  const unitSuffix = unit
    ? /^[%°]/.test(unit) ? unit : ` ${unit}`
    : "";
  if (expression.kind === "range" || expression.kind === "confidence_interval") {
    return expression.lower == null || expression.upper == null
      ? "Unresolved numeric expression"
      : `${expression.lower}–${expression.upper}${unitSuffix}`;
  }
  if (expression.value == null) return "Unresolved numeric expression";
  return `${expression.comparator} ${expression.value}${unitSuffix}`;
}

function formatAttributeRefs(attributeRefs: string[], fallback: string): string {
  const labels = Array.from(new Set(attributeRefs)).map(displayAttributeLabel);
  return labels.length > 0 ? labels.join(" · ") : fallback;
}

function formatFieldLinks(fieldLinks: QuantitativeTarget["field_links"]): string {
  return formatAttributeRefs(
    fieldLinks.map((link) => link.attribute_ref),
    "Document claim",
  );
}

const PRECEDENT_META: Record<PrecedentSignal["precedent"], { label: string; dot: string }> = {
  direct: { label: "Direct", dot: NEUTRAL_DOT },
  adjacent: { label: "Adjacent", dot: NEUTRAL_DOT },
  none: { label: "None found", dot: NEUTRAL_DOT },
  unknown: { label: "Unknown", dot: NEUTRAL_DOT },
};

const OUTCOME_META = {
  favorable: { label: "Favorable", dot: "bg-emerald-500" },
  mixed: { label: "Mixed", dot: "bg-amber-400" },
  unfavorable: { label: "Unfavorable", dot: "bg-[hsl(var(--tone-danger))]" },
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
        <span
          className="min-w-0 truncate"
          title={detail ? `${value} · ${detail}` : value}
        >
          <span className="font-medium text-foreground">{value}</span>
          {detail && <span className="text-muted-foreground"> · {detail}</span>}
        </span>
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
              className="min-w-0 flex-1 truncate text-muted-foreground transition-colors hover:text-foreground hover:underline motion-reduce:transition-none"
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
      <PageHeader title="Scout" description="One document’s targets against external evidence: whether its numbers hold up against live measurements, comparators, and development precedent." />
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
    results,
    selectedId,
    selectResult,
    removeResult,
    addResult,
    setResult,
    setBusy,
    setStage,
    setProgress,
    setError,
  } = useScoutSession();
  const {
    status: reviewStatus,
    history: reviewHistory,
    initialize: initializeReview,
    recordDecision,
    undoLast,
    finalize: finalizeReview,
    reset: resetReview,
  } = useScoutReviewSession();

  const importInputRef = useRef<HTMLInputElement>(null);
  const [showRunPanel, setShowRunPanel] = useState(!result);
  // Scout-only: the retrieval window, declared before the run and carried
  // on the draft so the continuation searches the same cohort.
  const [publishedSince, setPublishedSince] = useState("");

  useEffect(() => {
    if (result) setShowRunPanel(false);
  }, [result]);

  useEffect(() => {
    if (result && result.phase !== "target_review" && reviewStatus === "idle") {
      initializeReview(!isScoutResultFinal(result));
    }
  }, [initializeReview, result, reviewStatus]);

  async function handleRun(file: File) {
    if (results.length >= MAX_RESULTS_PER_TOOL) {
      setError(RESULT_LIMIT_MESSAGE);
      return;
    }
    setBusy(true);
    setError(null);
    setStage(null);
    setProgress(null);
    try {
      const res = await runScout([file], header, { publishedSince }, (s, p) => {
        setStage(s);
        setProgress(p ?? null);
      });
      addResult(res);
      if (res.phase === "target_review") resetReview();
      else initializeReview(!isScoutResultFinal(res));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  // Normalize a portable result once at the import boundary, then render only
  // the current runtime contract. Import never triggers retrieval.
  async function handleImport(file: File) {
    setError(null);
    if (results.length >= MAX_RESULTS_PER_TOOL) {
      setError(IMPORT_LIMIT_MESSAGE);
      return;
    }
    try {
      const raw = JSON.parse(await file.text());
      const parsed = unpackScoutResult(raw);
      if (!parsed || !Array.isArray(parsed.variables) || !Array.isArray(parsed.matches)) {
        throw new Error("not a scout result file");
      }
      setStage(null);
      setProgress(null);
      addResult(parsed, readResultIdentity(raw));
      initializeReview(!isScoutResultFinal(parsed));
    } catch (err) {
      setError(`Could not import result: ${(err as Error).message}`);
    }
  }

  function handleTargetDecision(targetId: string, decision: "approved" | "rejected") {
    if (!result || result.phase !== "target_review") return;
    const updateTarget = (target: QuantitativeTarget): QuantitativeTarget =>
      target.id === targetId ? { ...target, review_status: decision } : target;
    setResult({
      ...result,
      quantitative_ledger: {
        ...result.quantitative_ledger,
        targets: result.quantitative_ledger.targets.map(updateTarget),
      },
    });
  }

  function handleStatementDecision(unitId: string) {
    if (!result || result.phase !== "target_review") return;
    setResult({
      ...result,
      quantitative_ledger: {
        ...result.quantitative_ledger,
        reviews: result.quantitative_ledger.reviews.map((review) =>
          review.unit_id === unitId
            ? { ...review, review_status: "accepted_exclusion" as const }
            : review
        ),
      },
    });
  }

  function handleAcceptTargetRecommendations() {
    if (!result || result.phase !== "target_review") return;
    const updateTarget = (target: QuantitativeTarget): QuantitativeTarget => {
      if (target.review_status !== "needs_review") return target;
      if (target.ai_recommendation === "confirm") {
        return { ...target, review_status: "approved" };
      }
      if (target.ai_recommendation === "exclude") {
        return { ...target, review_status: "rejected" };
      }
      return target;
    };
    setResult({
      ...result,
      quantitative_ledger: {
        ...result.quantitative_ledger,
        targets: result.quantitative_ledger.targets.map(updateTarget),
      },
    });
  }

  async function handleContinueAnalysis() {
    if (!result || result.phase !== "target_review") return;
    if (pendingQuantitativeReviewCount(result) > 0) {
      setError("Resolve every document-target review item before continuing.");
      return;
    }
    setBusy(true);
    setError(null);
    setStage(null);
    setProgress(null);
    try {
      const completed = await continueScout(result, (s, p) => {
        setStage(s);
        setProgress(p ?? null);
      });
      setResult(completed);
      initializeReview(completed.phase === "evidence_review");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function handleQuantitativeReview(
    targetId: string,
    candidateIds: string[],
    selectedCandidateId: string | null,
  ) {
    if (!result) return;
    const previousScore = result.conformity.find((score) => score.target_id === targetId);
    if (!previousScore) return;
    const reviewedScore = reviewQuantitativeCandidateGroup(
      previousScore,
      candidateIds,
      selectedCandidateId,
    );
    if (reviewedScore === previousScore) return;
    const nextResult = {
      ...result,
      conformity: result.conformity.map((score) =>
        score.target_id === targetId ? reviewedScore : score
      ),
    };
    setResult(nextResult);
    recordDecision(
      {
        decision: selectedCandidateId == null ? "reject" : "approve",
        previousConformity: result.conformity,
      },
      pendingQuantitativeReviewCount(nextResult) > 0,
    );
  }

  function handleAcceptEvidenceRecommendations() {
    if (!result || result.phase !== "evidence_review") return;
    const conformity = applyEvidenceReviewRecommendations(result.conformity);
    if (conformity.every((score, index) => score === result.conformity[index])) return;
    const nextResult = { ...result, conformity };
    setResult(nextResult);
    recordDecision(
      { decision: "bulk", previousConformity: result.conformity },
      pendingQuantitativeReviewCount(nextResult) > 0,
    );
  }

  function handleUndoReview() {
    if (!result) return;
    const entry = undoLast();
    if (!entry) return;
    setResult({ ...result, conformity: entry.previousConformity });
  }

  function handleFinalizeReview() {
    if (!result || pendingQuantitativeReviewCount(result) > 0) {
      setError("Resolve every quantitative review candidate before finalizing.");
      return;
    }
    setError(null);
    setResult({ ...result, phase: "final" });
    finalizeReview();
  }

  return (
    <div className="flex flex-col gap-6">
      {(!result || showRunPanel) && (
        <RunPanel
          configuration={
            <ScoutConfiguration
              publishedSince={publishedSince}
              onPublishedSinceChange={setPublishedSince}
            />
          }
          busy={busy}
          onRun={(files) => handleRun(files.document)}
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
      {error && <ErrorMessage>{error}</ErrorMessage>}
      {result && <ContextValidationNotice result={result} />}
      {result && <RetrievalWindowNotice result={result} />}
      {result && result.phase === "target_review" && (
        <DocumentTargetReviewCheckpoint
          result={result}
          busy={busy}
          stage={stage}
          progress={progress}
          onTargetDecision={handleTargetDecision}
          onStatementDecision={handleStatementDecision}
          onAcceptRecommendations={handleAcceptTargetRecommendations}
          onContinue={handleContinueAnalysis}
          onNewAnalysis={() => setShowRunPanel(true)}
        />
      )}
      {result && result.phase === "evidence_review" && ["reviewing", "ready"].includes(reviewStatus) && (
        <QuantitativeReviewCheckpoint
          result={result}
          onNewAnalysis={() => setShowRunPanel(true)}
          onReview={handleQuantitativeReview}
          onAcceptRecommendations={handleAcceptEvidenceRecommendations}
          onUndo={handleUndoReview}
          canUndo={reviewHistory.length > 0}
          readyToFinalize={reviewStatus === "ready"}
          onFinalize={handleFinalizeReview}
        />
      )}
      {result && result.phase === "final" && reviewStatus === "final" && (
        <FieldGrid result={result} onNewAnalysis={() => setShowRunPanel(true)} />
      )}
    </div>
  );
}

function DocumentTargetReviewCheckpoint({
  result,
  busy,
  stage,
  progress,
  onTargetDecision,
  onStatementDecision,
  onAcceptRecommendations,
  onContinue,
  onNewAnalysis,
}: {
  result: ScoutResponse;
  busy: boolean;
  stage: string | null;
  progress: { completed: number; total: number } | null;
  onTargetDecision: (targetId: string, decision: "approved" | "rejected") => void;
  onStatementDecision: (unitId: string) => void;
  onAcceptRecommendations: () => void;
  onContinue: () => void;
  onNewAnalysis: () => void;
}) {
  const targets = result.quantitative_ledger.targets;
  const statements = result.quantitative_ledger.reviews.filter(
    (review) =>
      review.classification === "uncertain"
      || review.classification === "partial_target",
  );
  const pendingTargets = targets.filter((target) => target.review_status === "needs_review");
  const pendingStatements = statements.filter((review) => review.review_status === "needs_review");
  const total = targets.length + statements.length;
  const completed = total - pendingTargets.length - pendingStatements.length;
  const [selectedItem, setSelectedItem] = useState<string | null>(null);
  const itemKeys = [
    ...targets.map((target) => `target:${target.id}`),
    ...statements.map((statement) => `statement:${statement.unit_id}`),
  ];
  const firstPendingKey = pendingTargets[0]
    ? `target:${pendingTargets[0].id}`
    : pendingStatements[0]
      ? `statement:${pendingStatements[0].unit_id}`
      : itemKeys[0] ?? null;

  useEffect(() => {
    if (selectedItem && itemKeys.includes(selectedItem)) return;
    setSelectedItem(firstPendingKey);
  }, [firstPendingKey, itemKeys, selectedItem]);

  const target = selectedItem?.startsWith("target:")
    ? targets.find((item) => item.id === selectedItem.slice("target:".length))
    : undefined;
  const statement = selectedItem?.startsWith("statement:")
    ? statements.find((item) => item.unit_id === selectedItem.slice("statement:".length))
    : undefined;
  const linkedVariables = target
    ? target.field_links.flatMap((link) => {
        const variable = result.variables.find((item) => item.name === link.attribute_ref);
        return variable ? [{ link, variable }] : [];
      })
    : [];
  const confirmedCount = targets.filter((item) => item.review_status === "approved").length;
  const excludedCount =
    targets.filter((item) => item.review_status === "rejected").length
    + statements.filter((item) => item.review_status === "accepted_exclusion").length;
  const flaggedCount = pendingTargets.length + pendingStatements.length;
  const recommendedTargetCount = pendingTargets.filter(
    (item) => item.ai_recommendation === "confirm" || item.ai_recommendation === "exclude",
  ).length;
  const confirmRecommendationCount = pendingTargets.filter(
    (item) => item.ai_recommendation === "confirm",
  ).length;
  const excludeRecommendationCount = pendingTargets.filter(
    (item) => item.ai_recommendation === "exclude",
  ).length;
  const manualTargetCount = pendingTargets.length - recommendedTargetCount + pendingStatements.length;

  function nextPendingKey(currentKey: string): string | null {
    const remaining = [
      ...pendingTargets
        .filter((item) => `target:${item.id}` !== currentKey)
        .map((item) => `target:${item.id}`),
      ...pendingStatements
        .filter((item) => `statement:${item.unit_id}` !== currentKey)
        .map((item) => `statement:${item.unit_id}`),
    ];
    return remaining[0] ?? currentKey;
  }

  function decideTarget(targetId: string, decision: "approved" | "rejected") {
    const key = `target:${targetId}`;
    onTargetDecision(targetId, decision);
    if (target?.review_status === "needs_review") setSelectedItem(nextPendingKey(key));
  }

  function decideStatement(unitId: string) {
    const key = `statement:${unitId}`;
    onStatementDecision(unitId);
    setSelectedItem(nextPendingKey(key));
  }

  return (
    <DocumentSourceProvider blocks={result.blocks ?? []}>
      <section
        className={cn(
          "overflow-hidden rounded-xl border border-border/80 bg-card shadow-sm",
          SURFACE_ENTRY_MOTION,
        )}
      >
        <ReviewCheckpointHeader
          eyebrow="Target review"
          title="Review document targets"
          description="Confirm that each proposed number is a real document commitment—not background context, an example, or a rejected alternative."
          help={<>Scout has tied each item to a canonical document field and exact source passage. Confirm measurable targets before they shape retrieval and statistics. Excluded items remain in the audit ledger.</>}
          completed={completed}
          total={total}
          progressLabel="Document target review progress"
          actions={
            <>
              {pendingTargets.length + pendingStatements.length === 0 && (
                <Button size="sm" disabled={busy} onClick={onContinue}>
                  {busy ? "Continuing…" : "Continue to evidence"}
                </Button>
              )}
              <Button variant="ghost" size="sm" disabled={busy} onClick={onNewAnalysis}>
                New analysis
              </Button>
            </>
          }
        />

        <ReviewOverview
          description="Every source-verifiable proposal was reviewed against the complete document. Select an item to inspect its source and change the recommendation before retrieval begins."
          counts={
            <>
              {flaggedCount > 0 ? (
                <>
                  <ReviewCount dot="bg-emerald-500" label={`${confirmRecommendationCount} confirm recommended`} />
                  <ReviewCount dot="bg-muted-foreground/50" label={`${excludeRecommendationCount} exclude recommended`} />
                  <ReviewCount dot="bg-amber-400" label={`${manualTargetCount} needs review`} />
                </>
              ) : (
                <>
                  <ReviewCount dot="bg-emerald-500" label={`${confirmedCount} confirmed`} />
                  <ReviewCount dot="bg-muted-foreground/50" label={`${excludedCount} excluded`} />
                </>
              )}
            </>
          }
          actions={recommendedTargetCount > 0 ? (
            <Button size="sm" onClick={onAcceptRecommendations}>
              Accept {recommendedTargetCount} AI recommendations
            </Button>
          ) : undefined}
        >
              {targets.map((item) => {
                const presentation = targetReviewPresentation(item);
                const selected = selectedItem === `target:${item.id}`;
                return (
                  <ReviewListRow
                    key={item.id}
                    selected={selected}
                    onSelect={() => setSelectedItem(`target:${item.id}`)}
                    title={formatFieldLinks(item.field_links)}
                    subtitle={formatNumericExpression(item.expression)}
                    status={presentation.label}
                    tone={presentation.tone}
                    detail={item.ai_review_reason || "No reviewer explanation was returned; manual review is required."}
                  />
                );
              })}
              {statements.map((item) => {
                const pending = item.review_status === "needs_review";
                const selected = selectedItem === `statement:${item.unit_id}`;
                return (
                  <ReviewListRow
                    key={item.unit_id}
                    selected={selected}
                    onSelect={() => setSelectedItem(`statement:${item.unit_id}`)}
                    title={formatAttributeRefs(item.attribute_refs, "Document context")}
                    subtitle={item.classification === "partial_target"
                      ? "Partially resolved extraction"
                      : "Unresolved extraction"}
                    status={pending ? "Needs review" : "Excluded"}
                    tone={pending ? "warning" : "neutral"}
                    detail={statementReviewReason(item.reason)}
                  />
                );
              })}
        </ReviewOverview>

        {target ? (
          <ReviewDetailColumns
            left={
              <>
              <div className="flex items-center justify-between gap-3">
                <SectionLabel>Source passage</SectionLabel>
                <DocumentSourceTrace
                  blockIds={target.doc_block_ids}
                  spans={target.provenance_spans}
                />
              </div>
              <blockquote className="mt-3 border-l-2 border-border pl-3 text-xs leading-relaxed text-foreground/85">
                {target.quote}
              </blockquote>
              </>
            }
            right={
              <>
              <SectionLabel>Proposed measurable target</SectionLabel>
              <div className="mt-3 flex flex-wrap items-baseline gap-x-3 gap-y-1">
                <p className="text-xl font-semibold text-foreground">
                  {formatNumericExpression(target.expression)}
                </p>
                <span className="rounded-full border border-border px-2 py-0.5 text-[10px] font-medium capitalize text-muted-foreground">
                  {target.role}
                </span>
              </div>
              <dl className="mt-5 grid gap-x-5 gap-y-4 sm:grid-cols-2">
                {comparisonDimensions(target).map((dimension) => (
                  <div key={dimension} className="min-w-0">
                    <dt className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                      {dimensionLabel(dimension)}
                    </dt>
                    <dd className="mt-0.5 text-xs leading-relaxed text-foreground">
                      {semanticSlotLabel(target.semantic_profile[dimension])}
                    </dd>
                    <dd className="mt-1 text-[10px] leading-relaxed text-muted-foreground">
                      {comparisonRuleLabel(target.comparison_contract[dimension])}
                    </dd>
                  </div>
                ))}
              </dl>
              <div className="mt-5 border-t border-border/70 pt-4">
                <SectionLabel>Linked product fields</SectionLabel>
                <div className="mt-2 space-y-2">
                  {linkedVariables.map(({ link, variable }) => (
                    <div key={`${link.attribute_ref}:${link.relation}`} className="text-[11px] leading-relaxed">
                      <span className="font-medium text-foreground">
                        {displayAttributeLabel(variable.name)}
                      </span>
                      <span className="ml-2 capitalize text-muted-foreground">
                        {link.relation.replace("_", " ")}
                        {link.reason ? ` · ${link.reason}` : ""}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
              <ReviewRecommendation
                label={aiRecommendationPresentation(target.ai_recommendation).label}
                tone={aiRecommendationPresentation(target.ai_recommendation).tone}
              >
                {target.ai_review_reason || "No explanation was returned; review this proposal manually."}
              </ReviewRecommendation>
              </>
            }
          />
        ) : statement ? (
          <div className="p-5 sm:p-7">
            <div className="flex items-center justify-between gap-3">
              <SectionLabel>
                {statement.classification === "partial_target"
                  ? "Unresolved remainder"
                  : "Unresolved extraction"}
              </SectionLabel>
              <DocumentSourceTrace
                blockIds={[statement.block_id]}
                spans={[{ quote: statement.quote, block_ids: [statement.block_id] }]}
              />
            </div>
            <p className="mt-3 text-sm font-semibold text-foreground">
              {formatAttributeRefs(statement.attribute_refs, "Document context")}
            </p>
            <blockquote className="mt-3 max-w-4xl border-l-2 border-border pl-3 text-xs leading-relaxed text-foreground/85">
              {statement.quote}
            </blockquote>
            <div className="mt-4 flex max-w-4xl items-start gap-2 rounded-lg border border-border/70 bg-muted/20 p-3 text-xs leading-relaxed text-muted-foreground">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              <span>{statementReviewReason(statement.reason)}</span>
            </div>
          </div>
        ) : (
          <div className="px-5 py-9 sm:px-7">
            <p className="text-base font-semibold text-foreground">Document targets are resolved</p>
            <p className="mt-1 max-w-2xl text-xs leading-relaxed text-muted-foreground">
              Approved targets will shape target-specific queries and quantitative calibration. Rejected and
              uncertain statements remain traceable but cannot enter calculations.
            </p>
          </div>
        )}

        <footer className="flex flex-col-reverse gap-2 border-t border-border/80 bg-muted/15 px-5 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-7">
          <p className="text-[10px] leading-relaxed text-muted-foreground">
            {busy
              ? `${stage ? SCOUT_STEPS.find((item) => item.key === stage)?.label ?? stage : "Continuing analysis"}${progress ? ` · ${progress.completed}/${progress.total}` : ""}`
              : "Every decision is stored in the portable draft; no hidden server state is used."}
          </p>
          <div className="flex gap-2">
            {target && (
              <>
                <Button variant="outline" disabled={busy} onClick={() => decideTarget(target.id, "rejected")}>
                  Exclude as context
                </Button>
                <Button disabled={busy} onClick={() => decideTarget(target.id, "approved")}>
                  Confirm target
                </Button>
              </>
            )}
            {statement && (
              <Button disabled={busy} onClick={() => decideStatement(statement.unit_id)}>
                {statement.classification === "partial_target"
                  ? "Acknowledge unresolved remainder"
                  : "Acknowledge exclusion"}
              </Button>
            )}
            {!target && !statement && pendingTargets.length + pendingStatements.length === 0 && (
              <Button disabled={busy} onClick={onContinue}>
                {busy ? "Continuing…" : "Continue to evidence"}
              </Button>
            )}
          </div>
        </footer>
      </section>
    </DocumentSourceProvider>
  );
}

function ReviewCount({ dot, label }: { dot: string; label: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <span className={`h-1.5 w-1.5 rounded-full ${dot}`} />
      {label}
    </span>
  );
}

function ReviewCheckpointHeader({
  eyebrow,
  title,
  description,
  help,
  completed,
  total,
  progressLabel,
  actions,
}: {
  eyebrow: string;
  title: string;
  description: string;
  help: ReactNode;
  completed: number;
  total: number;
  progressLabel: string;
  actions?: ReactNode;
}) {
  return (
    <header className="border-b border-border/80 px-5 py-5 sm:px-7">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="flex items-center gap-1.5">
            <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
              {eyebrow}
            </p>
            <ReviewHelp>{help}</ReviewHelp>
          </div>
          <h2 className="mt-1 text-lg font-semibold text-foreground">{title}</h2>
          <p className="mt-1 max-w-2xl text-xs leading-relaxed text-muted-foreground">
            {description}
          </p>
        </div>
        {actions && <div className="flex items-center gap-2">{actions}</div>}
      </div>
      <div className="mt-4 flex items-center gap-3">
        <div
          className="h-1.5 min-w-0 flex-1 overflow-hidden rounded-full bg-muted"
          role="progressbar"
          aria-label={progressLabel}
          aria-valuemin={0}
          aria-valuemax={total}
          aria-valuenow={completed}
        >
          <div
            className="h-full rounded-full bg-foreground transition-[width] duration-base motion-reduce:transition-none"
            style={{ width: `${total ? (completed / total) * 100 : 100}%` }}
          />
        </div>
        <span className="shrink-0 text-[11px] tabular-nums text-muted-foreground">
          {completed} of {total} reviewed
        </span>
      </div>
    </header>
  );
}

function ReviewOverview({
  description,
  counts,
  actions,
  children,
}: {
  description: string;
  counts: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="border-b border-border/80 bg-muted/10 px-5 py-5 sm:px-7">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold text-foreground">Review overview</h3>
            <span className="rounded-full border border-border bg-card px-2 py-0.5 text-[9px] font-medium uppercase tracking-wide text-muted-foreground">
              AI prefilled
            </span>
          </div>
          <p className="mt-1 max-w-3xl text-[11px] leading-relaxed text-muted-foreground">
            {description}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex flex-wrap items-center gap-3 text-[10px] font-medium text-muted-foreground">
            {counts}
          </div>
          {actions}
        </div>
      </div>
      <div className="mt-4 max-h-72 overflow-y-auto rounded-lg border border-border/80 bg-card">
        <div className="divide-y divide-border/70">{children}</div>
      </div>
    </div>
  );
}

type ReviewTone = "positive" | "neutral" | "warning";

function ReviewListRow({
  selected,
  onSelect,
  title,
  subtitle,
  status,
  tone,
  detail,
}: {
  selected: boolean;
  onSelect: () => void;
  title: string;
  subtitle: string;
  status: string;
  tone: ReviewTone;
  detail: string;
}) {
  const statusClass = {
    positive: "border-emerald-200 bg-emerald-50 text-emerald-800",
    neutral: "border-border bg-muted/35 text-muted-foreground",
    warning: "border-amber-200 bg-amber-50 text-amber-800",
  }[tone];
  return (
    <button
      type="button"
      onClick={onSelect}
      className={`grid w-full gap-2 px-3 py-2.5 text-left transition-colors hover:bg-muted/35 sm:grid-cols-[minmax(0,0.9fr)_minmax(9rem,0.7fr)_minmax(0,1.4fr)] sm:items-center ${selected ? "bg-muted/45" : "bg-card"}`}
      aria-current={selected ? "true" : undefined}
    >
      <span className="min-w-0">
        <span className="block truncate text-[11px] font-medium text-foreground">{title}</span>
        <span className="mt-0.5 block truncate text-[10px] text-muted-foreground">{subtitle}</span>
      </span>
      <span className={`w-fit rounded-full border px-2 py-0.5 text-[9px] font-medium ${statusClass}`}>
        {status}
      </span>
      <span className="min-w-0 truncate text-[10px] text-muted-foreground">{detail}</span>
    </button>
  );
}

function ReviewDetailColumns({ left, right }: { left: ReactNode; right: ReactNode }) {
  return (
    <div className="grid lg:grid-cols-2">
      <div className="min-w-0 border-b border-border/80 p-5 sm:p-7 lg:border-b-0 lg:border-r">
        {left}
      </div>
      <div className="min-w-0 p-5 sm:p-7">{right}</div>
    </div>
  );
}

function ReviewRecommendation({
  label,
  tone,
  children,
}: {
  label: string;
  tone: ReviewTone;
  children: ReactNode;
}) {
  const accent = {
    positive: "text-emerald-700",
    neutral: "text-muted-foreground",
    warning: "text-amber-700",
  }[tone];
  return (
    <div className="mt-4 rounded-lg border border-border/70 bg-muted/20 p-3">
      <p className={`text-[10px] font-semibold uppercase tracking-wide ${accent}`}>
        AI recommendation · {label}
      </p>
      <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">{children}</p>
    </div>
  );
}

function statementReviewReason(reason: string): string {
  if (reason.includes("Source-verifiable targets were retained")) {
    const issue = reason.match(/\[([^\]]+)\]/)?.[1]?.replaceAll("_", " ");
    return `Validated targets from this passage were kept. A separate proposed mapping could not be verified and remains outside retrieval and statistics.${issue ? ` Structural issue: ${issue}.` : ""}`;
  }
  if (reason.includes("Target mapping rejected")) {
    const issue = reason.match(/\[([^\]]+)\]/)?.[1]?.replaceAll("_", " ");
    return `Scout could not create a complete, source-verifiable target from this statement. It remains outside retrieval and statistics.${issue ? ` Structural issue: ${issue}.` : ""}`;
  }
  if (reason.includes("model did not return one unique review")) {
    return "Scout could not resolve this statement into one reliable review decision. It remains outside retrieval and statistics.";
  }
  return reason;
}

function targetReviewPresentation(target: QuantitativeTarget): {
  label: string;
  tone: ReviewTone;
} {
  if (target.review_status === "approved") return { label: "Confirmed", tone: "positive" };
  if (target.review_status === "rejected") return { label: "Excluded", tone: "neutral" };
  if (target.ai_recommendation === "confirm") return { label: "Confirm recommended", tone: "positive" };
  if (target.ai_recommendation === "exclude") return { label: "Exclude recommended", tone: "neutral" };
  return { label: "Needs review", tone: "warning" };
}

function aiRecommendationPresentation(
  recommendation: QuantitativeTarget["ai_recommendation"],
): { label: string; tone: ReviewTone } {
  if (recommendation === "confirm") return { label: "Confirm", tone: "positive" };
  if (recommendation === "exclude") return { label: "Exclude", tone: "neutral" };
  return { label: "Review manually", tone: "warning" };
}

function evidenceReviewPresentation(measurements: Measurement[]): {
  label: string;
  tone: ReviewTone;
} {
  if (measurements.some((item) => item.admission_status === "approved")) {
    return { label: "Admitted", tone: "positive" };
  }
  if (measurements.every((item) => item.admission_status === "rejected")) {
    return { label: "Rejected", tone: "neutral" };
  }
  const pending = measurements.filter((item) => item.admission_status === "needs_review");
  if (pending.some((item) => item.ai_recommendation === "admit")) {
    return { label: "Admit recommended", tone: "positive" };
  }
  if (pending.length > 0 && pending.every((item) => item.ai_recommendation === "reject")) {
    return { label: "Reject recommended", tone: "neutral" };
  }
  return { label: "Needs review", tone: "warning" };
}

function semanticSlotLabel(slot: SemanticSlot | undefined): string {
  if (!slot) return "Not available";
  if (slot.state === "specified") return slot.value || "Specified";
  if (slot.state === "other") return slot.other || "Other";
  if (slot.state === "unknown") return "Unknown";
  return "Not specified";
}

function dimensionLabel(value: string): string {
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function comparisonDimensions(target: QuantitativeTarget): Array<keyof QuantitativeSemanticProfile> {
  return (Object.keys(target.comparison_contract) as Array<keyof QuantitativeSemanticProfile>)
    .filter((dimension) => target.comparison_contract[dimension].mode !== "unconstrained");
}

function comparisonRuleLabel(
  rule: QuantitativeTarget["comparison_contract"][keyof QuantitativeSemanticProfile] | undefined,
): string {
  if (!rule) return "Comparison scope unavailable";
  if (rule.mode === "unconstrained") return "Does not control comparison";
  if (rule.mode === "unknown") return `Scope needs review${rule.reason ? ` · ${rule.reason}` : ""}`;
  return `${rule.mode === "exact" ? "Exact" : "Compatible"} scope · ${rule.scope}`;
}

function evidenceUnitLabel(measurement: Measurement): string {
  const labels = [measurement.evidence_unit.group, measurement.evidence_unit.cohort]
    .map(semanticSlotLabel)
    .filter((label) => !["Not specified", "Not available", "Unknown"].includes(label));
  return labels.length > 0 ? labels.join(" · ") : "Source-level result";
}

function QuantitativeReviewCheckpoint({
  result,
  onNewAnalysis,
  onReview,
  onAcceptRecommendations,
  onUndo,
  canUndo,
  readyToFinalize,
  onFinalize,
}: {
  result: ScoutResponse;
  onNewAnalysis: () => void;
  onReview: (
    targetId: string,
    candidateIds: string[],
    selectedCandidateId: string | null,
  ) => void;
  onAcceptRecommendations: () => void;
  onUndo: () => void;
  canUndo: boolean;
  readyToFinalize: boolean;
  onFinalize: () => void;
}) {
  const allCandidates = result.conformity.flatMap((score) =>
    [...score.measurements, ...score.excluded_measurements].map((measurement) => ({
      score,
      measurement,
    })),
  ).filter(({ measurement }) =>
    measurement.evidence_mode === "prose"
      && ["needs_review", "approved", "rejected"].includes(measurement.admission_status)
  );
  const grouped = new Map<string, typeof allCandidates>();
  for (const item of allCandidates) {
    const unitId = item.measurement.evidence_unit_id || item.measurement.source_record_id;
    const key = `${item.score.target_id}::${unitId}`;
    grouped.set(key, [...(grouped.get(key) ?? []), item]);
  }
  const groups = Array.from(grouped.entries());
  const pendingGroups = groups.filter(([, items]) =>
    items.some(({ measurement }) => measurement.admission_status === "needs_review")
  );
  const groupKeys = groups.map(([key]) => key);
  const firstPendingGroupKey = pendingGroups[0]?.[0] ?? groupKeys[0] ?? null;
  const [selectedGroupKey, setSelectedGroupKey] = useState<string | null>(null);
  useEffect(() => {
    if (selectedGroupKey && groupKeys.includes(selectedGroupKey)) return;
    setSelectedGroupKey(firstPendingGroupKey);
  }, [firstPendingGroupKey, groupKeys, selectedGroupKey]);
  const current = groups.find(([key]) => key === selectedGroupKey) ?? pendingGroups[0] ?? groups[0];
  const recommendedCandidateId = current?.[1].find(
    ({ measurement }) =>
      measurement.admission_status === "needs_review"
      && measurement.ai_recommendation === "admit",
  )?.measurement.candidate_id ?? null;
  const [selectedCandidateId, setSelectedCandidateId] = useState<string | null>(null);
  useEffect(
    () => setSelectedCandidateId(recommendedCandidateId),
    [current?.[0], recommendedCandidateId],
  );
  if (!current) return null;

  const [currentGroupKey, groupItems] = current;
  const pendingItems = groupItems.filter(
    ({ measurement }) => measurement.admission_status === "needs_review",
  );
  const reviewItems = pendingItems.length > 0 ? pendingItems : groupItems;
  const score = groupItems[0].score;
  const multiple = reviewItems.length > 1;
  const activeItem = multiple
    ? reviewItems.find(({ measurement }) => measurement.candidate_id === selectedCandidateId)
      ?? reviewItems[0]
    : reviewItems[0];
  const measurement = activeItem?.measurement;
  const target: QuantitativeTarget | undefined = result.quantitative_ledger.targets.find(
    (item) => item.id === score.target_id,
  );
  const dimensions = measurement
    ? (target ? comparisonDimensions(target) : Object.keys(
        measurement.semantic_assessment.dimensions,
      )) as Array<keyof typeof measurement.semantic_assessment.dimensions>
    : [];
  const total = groups.length;
  const completed = total - pendingGroups.length;
  const admittedGroupCount = groups.filter(([, items]) =>
    items.some(({ measurement: item }) => item.admission_status === "approved")
  ).length;
  const rejectedGroupCount = groups.filter(([, items]) =>
    items.every(({ measurement: item }) => item.admission_status === "rejected")
  ).length;
  const recommendationSummary = evidenceReviewRecommendationSummary(result.conformity);
  const actionableRecommendations = recommendationSummary.admit + recommendationSummary.reject;

  function sourceFindingFor(item: (typeof allCandidates)[number]) {
    return result.matches.find(
      (match) => match.insight.id === item.measurement.insight_id,
    )?.insight.supporting_findings.find(
      (finding) => finding.url === item.measurement.url,
    );
  }

  function decideCurrent(selectedId: string | null) {
    if (pendingItems.length === 0) return;
    onReview(
      score.target_id,
      pendingItems.map(({ measurement: item }) => item.candidate_id),
      selectedId,
    );
    const nextKey = pendingGroups.find(([key]) => key !== currentGroupKey)?.[0];
    if (nextKey) setSelectedGroupKey(nextKey);
  }

  return (
    <DocumentSourceProvider blocks={result.blocks ?? []}>
      <section
        className={cn(
          "overflow-hidden rounded-xl border border-border/80 bg-card shadow-sm",
          SURFACE_ENTRY_MOTION,
        )}
      >
        <ReviewCheckpointHeader
          eyebrow="Evidence review"
          title="Review quantitative evidence"
          description="Decide whether each cited result measures the document target closely enough to enter the comparator statistics."
          help={<>Admit evidence only when it measures the same outcome, product, population, regimen, and time horizon as the document target. Rejected evidence remains in the audit trail but cannot enter statistics.</>}
          completed={completed}
          total={total}
          progressLabel="Quantitative evidence review progress"
          actions={
            <>
              {canUndo && (
                <Button variant="ghost" size="sm" onClick={onUndo}>Undo last decision</Button>
              )}
              {readyToFinalize && (
                <Button size="sm" onClick={onFinalize}>Finalize result</Button>
              )}
              <Button variant="ghost" size="sm" onClick={onNewAnalysis}>New analysis</Button>
            </>
          }
        />

        <ReviewOverview
          description="Every comparator was mapped to its document target. Select an item to inspect the cited result, dimension mapping, and recommendation before finalizing the evidence set."
          counts={
            <>
              {pendingGroups.length > 0 ? (
                <>
                  <ReviewCount dot="bg-emerald-500" label={`${recommendationSummary.admit} admit recommended`} />
                  <ReviewCount dot="bg-muted-foreground/50" label={`${recommendationSummary.reject} reject recommended`} />
                  <ReviewCount dot="bg-amber-400" label={`${recommendationSummary.flag} needs review`} />
                </>
              ) : (
                <>
                  <ReviewCount dot="bg-emerald-500" label={`${admittedGroupCount} admitted`} />
                  <ReviewCount dot="bg-muted-foreground/50" label={`${rejectedGroupCount} rejected`} />
                </>
              )}
            </>
          }
          actions={actionableRecommendations > 0 ? (
            <Button
              size="sm"
              onClick={onAcceptRecommendations}
            >
              Accept {actionableRecommendations} AI recommendations
            </Button>
          ) : undefined}
        >
          {groups.map(([key, items]) => {
            const representative = items.find(
              ({ measurement: item }) => item.admission_status === "needs_review",
            ) ?? items[0];
            const presentation = evidenceReviewPresentation(items.map((item) => item.measurement));
            const selected = key === currentGroupKey;
            const sourceTitle = sourceFindingFor(representative)?.title
              || representative.measurement.source_record_id
              || "Cited source";
            const rowTarget = result.quantitative_ledger.targets.find(
              (item) => item.id === representative.score.target_id,
            );
            return (
              <ReviewListRow
                key={key}
                selected={selected}
                onSelect={() => setSelectedGroupKey(key)}
                title={formatAttributeRefs(representative.score.attribute_refs, "Document claim")}
                subtitle={`${formatNumericExpression(representative.measurement.expression)} → ${rowTarget ? formatNumericExpression(rowTarget.expression) : representative.score.target_label}`}
                status={presentation.label}
                tone={presentation.tone}
                detail={sourceTitle}
              />
            );
          })}
        </ReviewOverview>

        <ReviewDetailColumns
          left={
            <>
            <div className="flex items-center justify-between gap-3">
              <SectionLabel>Document target</SectionLabel>
              <DocumentSourceTrace
                blockIds={score.doc_block_ids ?? []}
                spans={score.target_quote && score.doc_block_ids?.length
                  ? [{ quote: score.target_quote, block_ids: score.doc_block_ids }]
                : []}
              />
            </div>
            <p className="mt-3 text-base font-semibold text-foreground">
              {formatAttributeRefs(score.attribute_refs, "Document claim")}
            </p>
            <div className="mt-2 flex flex-wrap items-baseline gap-2">
              <span className="text-lg font-semibold text-foreground">
                {target ? formatNumericExpression(target.expression) : score.target_label}
              </span>
              {target && (
                <span className="rounded-full border border-border px-2 py-0.5 text-[10px] font-medium capitalize text-muted-foreground">
                  {target.role}
                </span>
              )}
            </div>
            <blockquote className="mt-3 border-l-2 border-border pl-3 text-xs leading-relaxed text-muted-foreground">
              {score.target_quote}
            </blockquote>
            </>
          }
          right={
            <>
            {multiple ? (
              <>
                <div className="flex items-center gap-1.5">
                  <SectionLabel>Choose one estimate</SectionLabel>
                  <ReviewHelp>
                    These values belong to the same source arm or cohort for this target.
                    Select the one that best represents the target, or choose “None apply.”
                    Distinct non-overlapping arms or cohorts are reviewed separately.
                  </ReviewHelp>
                </div>
                <p className="mt-1 text-[11px] text-muted-foreground">
                  Same evidence unit · {evidenceUnitLabel(reviewItems[0].measurement)}
                </p>
                <div className="mt-3 space-y-2" role="radiogroup" aria-label="Evidence estimate">
                  {reviewItems.map((item) => {
                    const option = item.measurement;
                    const selected = option.candidate_id === selectedCandidateId;
                    const sourceFinding = sourceFindingFor(item);
                    return (
                      <button
                        key={option.candidate_id}
                        type="button"
                        role="radio"
                        aria-checked={selected}
                        onClick={() => setSelectedCandidateId(option.candidate_id)}
                        className={`w-full rounded-lg border p-3 text-left transition-colors ${selected
                          ? "border-foreground/45 bg-muted/45"
                          : "border-border/70 hover:border-foreground/25 hover:bg-muted/20"}`}
                      >
                        <span className="flex items-start gap-3">
                          <span className={`mt-1 h-3.5 w-3.5 shrink-0 rounded-full border ${selected
                            ? "border-foreground bg-foreground shadow-[inset_0_0_0_3px_hsl(var(--card))]"
                            : "border-muted-foreground/60"}`} />
                          <span className="min-w-0">
                            <span className="block text-sm font-semibold text-foreground">
                              {formatNumericExpression(option.expression)}
                            </span>
                            <span className="mt-1 line-clamp-3 block text-xs leading-relaxed text-foreground/80">
                              {option.source_quote}
                            </span>
                            <span className="mt-1.5 block truncate text-[11px] text-muted-foreground">
                              {sourceFinding?.title || option.source_record_id || "Cited source"}
                            </span>
                          </span>
                        </span>
                      </button>
                    );
                  })}
                </div>
              </>
            ) : measurement ? (
              <>
                <SectionLabel>Cited evidence</SectionLabel>
                <p className="mt-3 text-base font-semibold text-foreground">
                  {formatNumericExpression(measurement.expression)}
                </p>
                <blockquote className="mt-3 border-l-2 border-border pl-3 text-xs leading-relaxed text-foreground/85">
                  {measurement.source_quote}
                </blockquote>
                <a
                  href={measurement.url}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-3 block truncate text-xs font-medium text-muted-foreground hover:text-foreground hover:underline"
                >
                  {sourceFindingFor(reviewItems[0])?.title || measurement.source_record_id || "Open cited source"}
                </a>
              </>
            ) : null}
            </>
          }
        />

        <div className="border-t border-border/80 px-5 py-5 sm:px-7">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <SectionLabel>Comparison check</SectionLabel>
            <div className="flex items-center gap-3 text-[10px] text-muted-foreground">
              <span>Mapped dimensions · your decision controls admission</span>
              {measurement?.url && (
                <a
                  href={measurement.url}
                  target="_blank"
                  rel="noreferrer"
                  className="font-medium hover:text-foreground hover:underline"
                >
                  Open source
                </a>
              )}
            </div>
          </div>
          {measurement ? <div className="mt-3 overflow-hidden rounded-lg border border-border/70">
            <div className="hidden grid-cols-[0.8fr_1fr_1fr_0.65fr] gap-4 bg-muted/35 px-4 py-2 text-[10px] font-medium uppercase tracking-wide text-muted-foreground sm:grid">
              <span>Dimension</span><span>Target</span><span>Evidence</span><span>Mapping</span>
            </div>
            {dimensions.map((dimension) => {
              const targetSlot = target?.semantic_profile[dimension];
              const comparisonRule = target?.comparison_contract[dimension];
              const mapped = measurement.semantic_assessment.dimensions[dimension];
              const compatibility = mapped?.compatibility.state ?? "unknown";
              return (
                <div
                  key={dimension}
                  className="grid gap-1 border-t border-border/70 px-4 py-3 first:border-t-0 sm:grid-cols-[0.8fr_1fr_1fr_0.65fr] sm:gap-4"
                >
                  <span className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground sm:text-xs sm:normal-case sm:tracking-normal">
                    {dimensionLabel(dimension)}
                  </span>
                  <span className="flex gap-2 text-xs text-foreground">
                    <span className="w-16 shrink-0 text-[10px] uppercase tracking-wide text-muted-foreground sm:hidden">Target</span>
                    <span>
                      {semanticSlotLabel(targetSlot)}
                      {comparisonRule && (
                        <span className="mt-1 block text-[10px] leading-relaxed text-muted-foreground">
                          {comparisonRuleLabel(comparisonRule)}
                        </span>
                      )}
                    </span>
                  </span>
                  <span className="flex gap-2 text-xs text-foreground">
                    <span className="w-16 shrink-0 text-[10px] uppercase tracking-wide text-muted-foreground sm:hidden">Evidence</span>
                    {semanticSlotLabel(mapped?.source)}
                  </span>
                  <span className="flex gap-2 text-xs font-medium text-muted-foreground">
                    <span className="w-16 shrink-0 text-[10px] uppercase tracking-wide sm:hidden">Mapping</span>
                    {compatibility === "yes" ? "Aligned" : compatibility === "no" ? "Different" : "Uncertain"}
                  </span>
                </div>
              );
            })}
          </div> : (
            <p className="mt-3 rounded-lg border border-dashed border-border px-4 py-5 text-xs text-muted-foreground">
              Select an estimate above to inspect how it maps to the document target.
            </p>
          )}
          {measurement && <p className="mt-3 text-[11px] leading-relaxed text-muted-foreground">
            {measurement.semantic_reason}
          </p>}
          {measurement && (
            <ReviewRecommendation
              label={measurement.ai_recommendation === "admit"
                ? "Admit"
                : measurement.ai_recommendation === "reject"
                  ? "Reject"
                  : "Review manually"}
              tone={measurement.ai_recommendation === "admit"
                ? "positive"
                : measurement.ai_recommendation === "reject"
                  ? "neutral"
                  : "warning"}
            >
              {measurement.ai_review_reason || "No complete independent recommendation was returned."}
            </ReviewRecommendation>
          )}
        </div>

        <footer className="flex flex-col-reverse gap-2 border-t border-border/80 bg-muted/15 px-5 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-7">
          <p className="text-[10px] leading-relaxed text-muted-foreground">
            One decision resolves this source evidence unit; its provenance remains traceable.
          </p>
          <div className="flex gap-2">
            {pendingItems.length > 0 ? (
              <>
                <Button variant="outline" onClick={() => decideCurrent(null)}>
                  {multiple ? "None apply" : "Reject comparator"}
                </Button>
                <Button
                  disabled={multiple && selectedCandidateId == null}
                  onClick={() => decideCurrent(
                    multiple ? selectedCandidateId : pendingItems[0].measurement.candidate_id,
                  )}
                >
                  {multiple ? "Use selected estimate" : "Admit comparator"}
                </Button>
              </>
            ) : (
              <span className="self-center text-[10px] font-medium text-muted-foreground">
                Decision recorded
              </span>
            )}
          </div>
        </footer>
      </section>
    </DocumentSourceProvider>
  );
}

function ReviewHelp({ children }: { children: ReactNode }) {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label="Explain this review step"
          className="rounded-full text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring motion-reduce:transition-none"
        >
          <CircleHelp className="h-3.5 w-3.5" />
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-72 p-3 text-xs leading-relaxed text-muted-foreground">
        {children}
      </PopoverContent>
    </Popover>
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

/**
 * The retrieval window this result was scoped to.
 *
 * Shown because the window removes evidence rather than hiding it: every count,
 * benchmark, and precedent below describes the cohort it admitted, so the same
 * document produces different numbers under different windows. The other
 * configuration values select which config a run uses and do not move the
 * numbers, which is why they are not echoed here.
 *
 * Neutral rather than a warning - a scoped run is a valid run - and absent when
 * no window was set, so an unscoped result gains no chrome. `published_since` is
 * optional because results saved before the window existed do not carry it.
 */
function RetrievalWindowNotice({ result }: { result: ScoutResponse }) {
  const since = formatWindowDate(result.published_since);
  if (!since) return null;

  return (
    <div
      role="status"
      className="flex items-start gap-2.5 rounded-lg border border-border bg-muted/40 px-3.5 py-3 text-xs text-foreground"
    >
      <CalendarRange className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" />
      <div className="min-w-0">
        <p className="font-medium">Scoped to evidence published since {since}</p>
        <p className="mt-0.5 leading-relaxed text-muted-foreground">
          Every count, benchmark, and precedent below describes only that window.
          Sources that publish no date, such as web pages, are included.
        </p>
      </div>
    </div>
  );
}

/**
 * Day precision, unlike `formatDate` - a window boundary is a specific day, and
 * rendering it to the month would misstate which evidence was admitted. Parsed as
 * local midnight so a UTC-negative timezone does not display the day before.
 */
function formatWindowDate(iso: string | undefined): string | null {
  if (!iso) return null;
  const d = new Date(`${iso}T00:00:00`);
  if (isNaN(d.getTime())) return null;
  return d.toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

/** True count of distinct sources cited anywhere in the result. */
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
  for (const observation of result.safety_observations ?? [])
    for (const finding of observation.supporting_findings ?? []) if (finding.url) urls.add(finding.url);
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
    ...(result.safety_observations ?? []).flatMap(
      (observation) => observation.supporting_findings ?? [],
    ),
  ];
}

function FieldGrid({
  result,
  onNewAnalysis,
}: {
  result: ScoutResponse;
  onNewAnalysis: () => void;
}) {
  const { results, selectedId, selectResult, removeResult } = useScoutSession();
  const priorities = useMemo(() => selectScoutPriorities(result), [result]);
  const digest = usePriorityDigest(
    selectedId
      ? {
          resultId: selectedId,
          authority: toolAuthority("scout"),
          orderNote: SCOUT_ORDER_NOTE,
          items: priorities,
          analysis: splitResultContext(result).analysis,
          blockIds: (result.blocks ?? []).map((block) => block.id),
          org: result.org ?? "",
          interventionClass: result.intervention_class ?? "",
          indication: result.indication ?? "",
        }
      : null,
  );
  const matches = result.matches ?? [];
  const variables = result.variables ?? [];
  const developmentLandscape = result.development_landscape ?? [];
  const safetyObservations = result.safety_observations ?? [];
  const [query, setQuery] = useState("");
  const [relationFilter, setRelationFilter] = useState<"all" | Match["relation"]>("all");
  const [resultTab, setResultTab] = useState("fields");
  const [traceFocusBlockId, setTraceFocusBlockId] = useState<string | null>(null);
  const openBlockInTrace = useCallback((blockId: string) => {
    setTraceFocusBlockId(blockId);
    setResultTab("trace");
  }, []);
  const consumeTraceFocus = useCallback((blockId: string) => {
    setTraceFocusBlockId((current) => current === blockId ? null : current);
  }, []);
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
    for (const attributeRef of score.attribute_refs) {
      const scores = conformityByVariable.get(attributeRef) ?? [];
      scores.push(score);
      conformityByVariable.set(attributeRef, scores);
    }
  }
  const precedentByVariable = new Map<string, PrecedentSignal>();
  for (const signal of result.precedents ?? []) {
    precedentByVariable.set(signal.attribute_ref, signal);
  }

  const rows = variables
    .map((variable) => {
      const variableMatches = matchesByVariable.get(variable.name) ?? [];
      const sortedMatches = sortMatchesForReading(variableMatches);
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
  const unresolvedFields = variables.filter(
    (variable) => !variable.target_resolved,
  );
  const unresolvedFieldCount = unresolvedFields.length;

  return (
    <DocumentSourceProvider
      blocks={result.blocks ?? []}
      onOpenInTrace={openBlockInTrace}
    >
      <div className="flex flex-col gap-4">
      <CollapsibleCard
        title={`${variables.length} fields`}
        subtitle={`${distinctSourceCount(result).toLocaleString()} sources · ${
          result.stats?.insights ?? 0
        } insights`}
        contentClassName="p-0"
        trailing={
          <>
          <RunHistory
            runs={results}
            selectedId={selectedId}
            onSelect={selectResult}
            onRemove={removeResult}
            label={(value) => runLabel(value, "scout")}
          />
          <FinalResultActions
            onNewAnalysis={onNewAnalysis}
            download={{
              filename: scoutResultFilename(result),
              data: packScoutResult(result),
            }}
          />
          </>
        }
      >
        <Tabs value={resultTab} onValueChange={setResultTab}>
          <div className="overflow-x-auto border-b border-border/80 px-5 pt-3 sm:px-6">
            <TabsList className="min-w-max border-b-0">
              <TabsTrigger value="fields">Fields</TabsTrigger>
              {developmentLandscape.length > 0 && (
                <TabsTrigger value="landscape">Landscape</TabsTrigger>
              )}
              {safetyObservations.length > 0 && (
                <TabsTrigger value="safety">Safety</TabsTrigger>
              )}
              <TabsTrigger value="map">Evidence map</TabsTrigger>
              <TabsTrigger value="trace">Documents</TabsTrigger>
            </TabsList>
          </div>
          <TabsContent value="fields" className="mt-0">
            {(unresolvedFieldCount > 0 || result.quantitative_ledger.status === "uncertain") && (
              <div className="flex items-start gap-2 border-b border-border/80 bg-muted/20 px-5 py-3 text-xs text-muted-foreground sm:px-6">
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                <div className="space-y-1">
                  {unresolvedFieldCount > 0 && (
                    <div>
                      <p>
                        Document interpretation stopped before retrieval because {unresolvedFieldCount} {unresolvedFieldCount === 1 ? "field" : "fields"} could not be bound safely.
                      </p>
                      <details className="mt-1.5">
                        <summary className="cursor-pointer font-medium text-foreground/80">
                          Review unresolved fields
                        </summary>
                        <ul className="mt-1.5 space-y-1 pl-4">
                          {unresolvedFields.map((variable) => (
                            <li key={variable.name} className="list-disc">
                              <span className="font-medium text-foreground/80">
                                {displayAttributeLabel(variable.name)}:
                              </span>{" "}
                              {variable.target_resolution_reason || "No validated decision was returned."}
                            </li>
                          ))}
                        </ul>
                      </details>
                    </div>
                  )}
                  {result.quantitative_ledger.status === "uncertain" && (
                    <p>
                      Some numeric statements remained unresolved after one retry. They were retained for audit and excluded from quantitative calibration; the verified document claims still proceeded through evidence retrieval.
                    </p>
                  )}
                </div>
              </div>
            )}
            <div className="px-5 pt-5 sm:px-6">
              <PriorityPanel
                attribution="by Scout"
                items={priorities}
                emptyMessage={SCOUT_EMPTY_MESSAGE}
                orderNote={SCOUT_ORDER_NOTE}
                digest={digest?.state === "ready" ? digest.digest.digest : undefined}
                nominations={digest?.state === "ready" ? digest.digest.nominations : []}
                digestLoading={digest?.state === "loading"}
              />
            </div>
            <div className="flex flex-col gap-2 border-b border-border/80 bg-muted/10 px-5 py-3 sm:flex-row sm:items-center sm:px-6">
              <label className="relative min-w-0 flex-1 sm:max-w-xs">
                <span className="sr-only">Search fields</span>
                <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                <input
                  type="search"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Find a field…"
                  className="h-8 w-full rounded-md border border-input bg-card pl-8 pr-3 text-xs outline-none transition-colors placeholder:text-muted-foreground focus:border-foreground/30 focus:ring-2 focus:ring-ring/10 motion-reduce:transition-none"
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
                quantitativeTargetStatus={row.variable.quantitative_target_status}
                quantitativeTargetStatusReason={row.variable.quantitative_target_status_reason}
                targetResolved={row.variable.target_resolved}
                targetResolutionReason={row.variable.target_resolution_reason}
                documentTarget={row.variable.document_target}
                documentSpans={row.variable.document_spans}
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
          {safetyObservations.length > 0 && (
            <TabsContent value="safety" className="mt-0">
              <SafetyObservations observations={safetyObservations} />
            </TabsContent>
          )}
          <TabsContent value="map" className="mt-0">
            <ScoutEvidenceMap result={result} />
          </TabsContent>
          <TabsContent value="trace" className="mt-0">
            <ScoutDocumentTrace
              result={result}
              focusBlockId={traceFocusBlockId}
              onFocusBlockConsumed={consumeTraceFocus}
            />
          </TabsContent>
        </Tabs>
        <SourceAttributions
          findings={resultFindings(result)}
          className="border-t border-border/80 px-5 py-3 sm:px-6"
        />
      </CollapsibleCard>
      </div>
    </DocumentSourceProvider>
  );
}

const PROJECTION_RELATIONSHIP_FILTERS: Array<{
  value: ProjectionRelationshipFilter;
  label: string;
}> = [
  { value: "all", label: "All relationships" },
  { value: "direct", label: "Direct" },
  { value: "analogous", label: "Analogous" },
  { value: "adjacent", label: "Adjacent" },
  { value: "unrelated", label: "Unrelated" },
  { value: "unknown", label: "Unknown" },
];

function ProjectionToolbar({
  query,
  onQueryChange,
  relationship,
  onRelationshipChange,
  searchLabel,
  placeholder,
  visibleCount,
  totalCount,
  recordLabel,
}: {
  query: string;
  onQueryChange: (value: string) => void;
  relationship: ProjectionRelationshipFilter;
  onRelationshipChange: (value: ProjectionRelationshipFilter) => void;
  searchLabel: string;
  placeholder: string;
  visibleCount: number;
  totalCount: number;
  recordLabel: string;
}) {
  return (
    <div className="flex flex-col gap-2 border-b border-border/80 bg-muted/10 px-5 py-3 sm:flex-row sm:items-center sm:px-6">
      <label className="relative min-w-0 flex-1 sm:max-w-xs">
        <span className="sr-only">{searchLabel}</span>
        <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
        <input
          type="search"
          value={query}
          onChange={(event) => onQueryChange(event.target.value)}
          placeholder={placeholder}
          className="h-8 w-full rounded-md border border-input bg-card pl-8 pr-3 text-xs outline-none transition-colors placeholder:text-muted-foreground focus:border-foreground/30 focus:ring-2 focus:ring-ring/10 motion-reduce:transition-none"
        />
      </label>
      <Select
        value={relationship}
        onValueChange={(value) =>
          onRelationshipChange(value as ProjectionRelationshipFilter)
        }
      >
        <SelectTrigger
          aria-label="Filter by relationship to the uploaded product"
          className="h-8 w-full bg-card sm:w-40"
        >
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {PROJECTION_RELATIONSHIP_FILTERS.map((option) => (
            <SelectItem key={option.value} value={option.value}>
              {option.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <p
        role="status"
        aria-live="polite"
        className="text-[11px] text-muted-foreground sm:ml-auto"
      >
        {visibleCount} of {totalCount} {recordLabel}
      </p>
    </div>
  );
}

function ProjectionRoleLabels({
  relationship,
  sourceRole,
}: {
  relationship: TargetRelationship;
  sourceRole: SourceRole;
}) {
  return (
    <div className="mt-2 flex flex-wrap items-center gap-2">
      <Badge variant="outline">{relationshipLabel(relationship)}</Badge>
      {sourceRole !== "unknown" && (
        <span className="text-[11px] text-muted-foreground">
          {sourceRoleLabel(sourceRole)}
        </span>
      )}
    </div>
  );
}

function ContextualProjectionNote({
  relationship,
  kind,
}: {
  relationship: TargetRelationship;
  kind: "development record" | "safety observation";
}) {
  if (!isContextualRelationship(relationship)) return null;
  return (
    <p className="mb-3 max-w-4xl rounded-md border border-border/80 bg-card px-3 py-2 text-[11px] leading-relaxed text-muted-foreground">
      Context only. This {kind} concerns {relationship === "analogous" ? "an analogous product" : "adjacent evidence"} and does not describe the uploaded product.
    </p>
  );
}

function DevelopmentLandscape({ programs }: { programs: DevelopmentProgram[] }) {
  const [query, setQuery] = useState("");
  const [relationship, setRelationship] =
    useState<ProjectionRelationshipFilter>("all");
  const normalizedQuery = query.trim().toLowerCase();
  const relationshipMatches = filterProjectionsByRelationship(programs, relationship);
  const visible = relationshipMatches.filter(
    (program) =>
      !normalizedQuery ||
      [program.name, ...program.sponsors, ...program.phases, ...program.statuses]
        .join(" ")
        .toLowerCase()
        .includes(normalizedQuery),
  );
  return (
    <section>
      <ProjectionToolbar
        query={query}
        onQueryChange={setQuery}
        relationship={relationship}
        onRelationshipChange={setRelationship}
        searchLabel="Search development records"
        placeholder="Find a development record…"
        visibleCount={visible.length}
        totalCount={programs.length}
        recordLabel="structured records"
      />
      {visible.map((program) => (
        <details key={program.projection_id} className="group/program border-b border-border/80 last:border-b-0">
          <summary className="flex cursor-pointer select-none items-start gap-4 px-5 py-4 outline-none transition-colors hover:bg-muted/25 focus-visible:bg-muted/25 focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring/20 group-open/program:bg-muted/15 sm:px-6 [&::-webkit-details-marker]:hidden motion-reduce:transition-none">
            <div className="min-w-0 flex-1">
              <h3 className="truncate text-sm font-semibold text-foreground">{program.name}</h3>
              <ProjectionRoleLabels
                relationship={program.target_relationship}
                sourceRole={program.source_role}
              />
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
              <ChevronDown className="h-4 w-4 text-muted-foreground transition-transform group-open/program:rotate-180 motion-reduce:transition-none" />
            </div>
          </summary>
          <div className={cn("border-t border-border/70 bg-muted/15 px-5 py-4 sm:px-6", DISCLOSURE_MOTION)}>
            <ContextualProjectionNote
              relationship={program.target_relationship}
              kind="development record"
            />
            {program.target_relationship_reason && (
              <p className="mb-3 max-w-4xl text-[11px] leading-relaxed text-muted-foreground">
                {program.target_relationship_reason}
              </p>
            )}
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
          No development records match this view.
        </p>
      )}
    </section>
  );
}

function SafetyObservations({
  observations,
}: {
  observations: SafetyObservation[];
}) {
  const [query, setQuery] = useState("");
  const [relationship, setRelationship] =
    useState<ProjectionRelationshipFilter>("all");
  const sections = groupSafetyObservations(observations, { query, relationship });
  const visibleCount = sections.reduce(
    (count, section) => count + section.observations.length,
    0,
  );
  return (
    <section>
      <ProjectionToolbar
        query={query}
        onQueryChange={setQuery}
        relationship={relationship}
        onRelationshipChange={setRelationship}
        searchLabel="Search safety observations"
        placeholder="Find a product or safety record…"
        visibleCount={visibleCount}
        totalCount={observations.length}
        recordLabel="observations"
      />
      {sections.map((section) => {
        const headingId = `safety-${section.key}-heading`;
        return (
          <section
            key={section.key}
            aria-labelledby={headingId}
            className="border-b border-border/80 last:border-b-0"
          >
            <header className="bg-muted/15 px-5 py-4 sm:px-6">
              <h3 id={headingId} className="text-sm font-semibold text-foreground">
                {section.title}
              </h3>
              <p className="mt-1 max-w-3xl text-xs leading-relaxed text-muted-foreground">
                {section.description}
              </p>
            </header>
            {section.observations.map((observation) => {
              const count = safetyObservationCountLabel(observation);
              return (
                <details
                  key={observation.projection_id}
                  className="group/safety border-t border-border/70"
                >
                  <summary className="flex min-h-16 cursor-pointer select-none items-start gap-4 px-5 py-4 outline-none transition-colors hover:bg-muted/20 focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring/30 group-open/safety:bg-muted/10 sm:px-6 [&::-webkit-details-marker]:hidden motion-reduce:transition-none">
                    <div className="min-w-0 flex-1">
                      <p className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                        {safetyRecordTypeLabel(observation.record_type)} · {safetySourceSystemLabel(observation.source_system)}
                      </p>
                      <h4 className="mt-1 text-sm font-semibold text-foreground">
                        {observation.product_name}
                      </h4>
                      <p className="mt-1 max-w-4xl text-xs leading-relaxed text-muted-foreground">
                        {observation.label}
                      </p>
                      <ProjectionRoleLabels
                        relationship={observation.target_relationship}
                        sourceRole={observation.source_role}
                      />
                    </div>
                    <div className="flex shrink-0 items-center gap-3 pt-0.5">
                      {count && (
                        <span className="text-xs tabular-nums text-muted-foreground">
                          {count}
                        </span>
                      )}
                      <ChevronDown
                        aria-hidden="true"
                        className="h-4 w-4 text-muted-foreground transition-transform group-open/safety:rotate-180 motion-reduce:transition-none"
                      />
                    </div>
                  </summary>
                  <div className="border-t border-border/70 bg-muted/10 px-5 py-4 sm:px-6">
                    <ContextualProjectionNote
                      relationship={observation.target_relationship}
                      kind="safety observation"
                    />
                    {observation.detail && (
                      <p className="max-w-4xl text-xs leading-relaxed text-foreground/90">
                        {observation.detail}
                      </p>
                    )}
                    {observation.qualification && (
                      <p className="mt-2 max-w-4xl text-[11px] leading-relaxed text-muted-foreground">
                        {observation.qualification}
                      </p>
                    )}
                    {observation.target_relationship_reason && (
                      <p className="mt-3 max-w-4xl text-[11px] leading-relaxed text-muted-foreground">
                        Relationship: {observation.target_relationship_reason}
                      </p>
                    )}
                    {observation.attribute_refs.length > 0 && (
                      <p className="mt-2 text-[11px] text-muted-foreground">
                        Retrieved for {observation.attribute_refs.map(displayAttributeLabel).join(" · ")}
                      </p>
                    )}
                    <SourceList findings={observation.supporting_findings} />
                  </div>
                </details>
              );
            })}
          </section>
        );
      })}
      {sections.length === 0 && (
        <p className="px-6 py-10 text-center text-sm text-muted-foreground">
          No safety observations match this view.
        </p>
      )}
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
  quantitativeTargetStatus,
  quantitativeTargetStatusReason,
  targetResolved,
  targetResolutionReason,
  documentTarget,
  documentSpans,
}: {
  name: string;
  description: string;
  matches: Match[];
  assessment: EvidenceAssessment | null;
  conformities: Conformity[];
  precedent: PrecedentSignal | null;
  quantitativeTargetStatus: "not_evaluated" | "present" | "not_applicable" | "uncertain";
  quantitativeTargetStatusReason: string;
  targetResolved: boolean;
  targetResolutionReason: string;
  documentTarget: string;
  documentSpans: DocumentSpan[];
}) {
  const evidenceMeta = assessment ? EVIDENCE_META[assessment.strength] : null;
  const precedentMeta = precedent ? precedentView(precedent) : null;
  const counts = relationCounts(matches);
  const comparatorCount = conformities.reduce(
    (total, score) => total + score.benchmark_count,
    0,
  );
  const hasDocumentTarget = Boolean(documentTarget.trim() || assessment?.doc_target?.trim());
  const targetNotStated = targetResolved && !hasDocumentTarget;
  return (
    <details className="group/field border-b border-border/80 last:border-b-0">
      <summary className="flex cursor-pointer select-none items-start justify-between gap-4 px-5 py-4 outline-none transition-colors hover:bg-muted/25 focus-visible:bg-muted/25 focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring/20 group-open/field:bg-muted/15 sm:px-6 [&::-webkit-details-marker]:hidden motion-reduce:transition-none">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2">
            <h3 className="text-sm font-semibold text-foreground">{displayAttributeLabel(name)}</h3>
          </div>
          <p className="mt-1 line-clamp-1 text-xs leading-relaxed text-muted-foreground">
            {description}
          </p>
          {targetNotStated ? (
            <p className="mt-2.5 text-xs font-medium text-muted-foreground">
              Not stated in document
              <span className="font-normal text-muted-foreground/70">
                {" "}· No document target was available for evidence analysis.
              </span>
            </p>
          ) : (
            <div className="mt-2.5 grid gap-x-6 gap-y-1.5 sm:grid-cols-2 xl:grid-cols-[minmax(0,1.35fr)_minmax(0,0.9fr)_minmax(0,1.2fr)_minmax(0,0.9fr)]">
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
                value={conformities.length > 0
                    ? countLabel(conformities.length, "numeric target")
                    : quantitativeTargetStatus === "not_applicable"
                      ? "No numeric target stated"
                      : quantitativeTargetStatus === "uncertain"
                        ? "Needs review"
                        : "Not evaluated"}
                detail={conformities.length > 0
                    ? countLabel(comparatorCount, "admitted comparator")
                    : undefined}
                dot={quantitativeTargetStatus === "present" ? TARGET_ALIGNMENT_DOT : undefined}
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
          )}
        </div>
        <ChevronDown className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground transition-transform group-open/field:rotate-180 motion-reduce:transition-none" />
      </summary>

      <div className={cn("space-y-3 border-t border-border/70 bg-muted/15 px-5 py-5 sm:px-6", DISCLOSURE_MOTION)}>
        {targetNotStated && (
          <div className="rounded-lg border border-border/80 bg-card px-4 py-3.5">
            <SectionLabel>Document target</SectionLabel>
            <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
              Not stated in document. Scout did not run evidence analysis for this field.
            </p>
          </div>
        )}
        {!targetResolved && (
          <div className="rounded-lg border border-border/80 bg-card px-4 py-3.5">
            <SectionLabel>Document interpretation · unresolved</SectionLabel>
            <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
              {targetResolutionReason || "No validated document-claim decision was returned."}
            </p>
          </div>
        )}
        {assessment?.doc_target && (
          <div className="rounded-lg border border-border/80 bg-card px-4 py-3.5">
            <div className="flex items-center justify-between gap-3">
              <SectionLabel>Document target · AI extracted</SectionLabel>
              <DocumentSourceTrace blockIds={assessment.doc_block_ids} spans={documentSpans} />
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
          <div className="space-y-5">
            {conformities.length > 1 && (
              <p className="text-[11px] leading-relaxed text-muted-foreground">
                The document states {conformities.length} distinct numeric targets for this field.
                Each target keeps its own semantic qualifiers, comparator cohort, and distribution.
              </p>
            )}
            {conformities.map((conformity) => (
              <ConformityBlock
                key={conformity.target_id}
                conformity={conformity}
                matches={matches}
              />
            ))}
          </div>
        )}
        {!targetNotStated && conformities.length === 0 && quantitativeTargetStatusReason && (
          <div className="rounded-lg border border-border/80 bg-card px-4 py-3.5">
            <SectionLabel>Evidence · quantitative calibration</SectionLabel>
            <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
              {quantitativeTargetStatusReason}
            </p>
          </div>
        )}
        {assessment && evidenceMeta && (
          <EvidenceBlock assessment={assessment} evidenceMeta={evidenceMeta} matches={matches} />
        )}
        {precedent && precedentMeta && (
          <PrecedentBlock precedent={precedent} precedentMeta={precedentMeta} matches={matches} />
        )}
        {!targetNotStated && <MatchesBlock matches={matches} />}
      </div>
    </details>
  );
}

function ConformityBlock({
  conformity,
  matches,
}: {
  conformity: Conformity;
  matches: Match[];
}) {
  const targetLabel =
    conformity.target_label ||
    `${conformity.comparator} ${conformity.target_value}${conformity.unit}`;
  const formatBenchmark = (value: number | null) =>
    value == null ? "—" : `${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}${conformity.unit}`;
  const targetPosition = conformity.benchmark_minimum == null || conformity.benchmark_maximum == null
    ? "—"
    : conformity.target_value < conformity.benchmark_minimum
      ? "Below observed range"
      : conformity.target_value > conformity.benchmark_maximum
        ? "Above observed range"
        : conformity.benchmark_count < 4 || conformity.ambition_percentile == null
          ? "Within observed range"
          : `${formatOrdinal(Math.round(conformity.ambition_percentile * 100))} ambition percentile`;
  const hasInformativeQuartiles = conformity.benchmark_count >= 4;
  const hasInformativeDeviation = conformity.benchmark_count >= 3;
  const coverageLabel = {
    insufficient: "Insufficient basis",
    limited: "Limited basis",
    sufficient: "Broader verified basis",
  }[conformity.calibration_status];
  const targetRoleLabel = {
    threshold: "Threshold",
    optimal: "Optimal",
    other: "Other target",
  }[conformity.target_role];
  // An ambiguous source and a source we failed to map are different claims and
  // are counted separately.
  const uncertainSources = conformity.source_dispositions.filter(
    (item) => item.status === "uncertain",
  );
  const unassessedSources = conformity.source_dispositions.filter(
    (item) => item.status === "not_assessed",
  );
  const consideredSources = conformity.source_dispositions.length;
  const otherExcluded = conformity.excluded_measurements;

  return (
    <section className="rounded-xl border border-border/80 bg-card p-5 sm:p-7">
      <div className="flex items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <SectionLabel>Evidence · quantitative calibration</SectionLabel>
          <span className="rounded-full border border-border bg-muted/40 px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
            {targetRoleLabel}
          </span>
        </div>
        <DocumentSourceTrace
          blockIds={conformity.doc_block_ids}
          spans={conformity.target_quote && conformity.doc_block_ids?.length
            ? [{ quote: conformity.target_quote, block_ids: conformity.doc_block_ids }]
            : []}
        />
      </div>
      <p className="mt-0.5 text-[11px] text-muted-foreground/80">
        AI-mapped prose remains a review candidate. Only explicitly admitted or
        typed structured evidence enters descriptive statistics.
      </p>
      <p className="mt-1 text-[11px] text-muted-foreground">
        Target <span className="text-foreground">{targetLabel}</span>
      </p>
      <blockquote className="mt-2 border-l-2 border-border pl-3 text-xs leading-relaxed text-foreground">
        {conformity.target_quote}
      </blockquote>

      {conformity.benchmark_count > 0 ? (
        <>
          <dl className="mt-4 grid grid-cols-2 overflow-hidden rounded-lg border border-border/70 sm:grid-cols-3">
            <StatCell label="External median" value={formatBenchmark(conformity.benchmark_median)} />
            <StatCell
              label="Middle 50%"
              value={hasInformativeQuartiles
                ? `${formatBenchmark(conformity.benchmark_lower_quartile)}–${formatBenchmark(conformity.benchmark_upper_quartile)}`
                : "Not shown"}
              detail={hasInformativeQuartiles ? undefined : "Not presented below 4 comparators"}
            />
            <StatCell label="Observed range" value={`${formatBenchmark(conformity.benchmark_minimum)}–${formatBenchmark(conformity.benchmark_maximum)}`} />
            <StatCell
              label="Mean · observed SD"
              value={hasInformativeDeviation
                ? `${formatBenchmark(conformity.benchmark_mean)} · ${formatBenchmark(conformity.benchmark_standard_deviation)}`
                : `${formatBenchmark(conformity.benchmark_mean)} · not shown`}
              detail={hasInformativeDeviation ? undefined : "SD not presented below 3 comparators"}
            />
            <StatCell label="Target position" value={targetPosition} />
            <StatCell label="Evidence basis" value={`${conformity.benchmark_count} comparator${conformity.benchmark_count === 1 ? "" : "s"}`} detail={coverageLabel} />
          </dl>
          <p className="mt-2 text-[10px] leading-relaxed text-muted-foreground/70">
            These values describe this selected comparator cohort only. Small cohorts intentionally
            omit unstable distribution summaries. They are not population uncertainty or likelihood of success.
          </p>
        </>
      ) : (
        <div className="mt-4 rounded-lg border border-border/70 bg-muted/20 px-4 py-3">
          <p className="text-xs font-medium text-foreground">No direct comparator cohort</p>
          <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">
            {conformity.excluded_measurements.length > 0
              ? "Complete source measurements were retained below, but none were comparable atomic scalars in the target unit. No statistics were calculated."
              : "The reviewed source passages did not yield a complete claim-compatible scalar. No statistics were calculated."}
          </p>
        </div>
      )}

      {(conformity.benchmark_count > 0 || conformity.excluded_measurements.length > 0) && (
        <ComparatorDistributionPlot conformity={conformity} />
      )}

      {consideredSources > 0 && (
        <div className="mt-3 text-[10px] text-muted-foreground/70">
          <p>
            {consideredSources} source passage{consideredSources === 1 ? "" : "s"} reviewed
            {uncertainSources.length > 0 ? ` · ${uncertainSources.length} unresolved` : ""}
            {unassessedSources.length > 0 ? ` · ${unassessedSources.length} not assessed` : ""}
            {uncertainSources.length === 0 && unassessedSources.length === 0
              ? " · all resolved"
              : ""}
          </p>
          {[
            {
              key: "unresolved",
              label: "Review source passages the model could not resolve",
              items: uncertainSources,
            },
            {
              key: "not-assessed",
              label: "Review source passages this run could not assess",
              items: unassessedSources,
            },
          ]
            .filter((group) => group.items.length > 0)
            .map((group) => (
              <details key={group.key} className="group/unresolved mt-1.5">
                <summary className="inline-flex cursor-pointer select-none items-center gap-1.5 rounded-md px-1.5 py-1 font-medium outline-none transition-colors hover:bg-muted hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/20 [&::-webkit-details-marker]:hidden motion-reduce:transition-none">
                  {group.label}
                  <ChevronDown className="h-3 w-3 transition-transform group-open/unresolved:rotate-180 motion-reduce:transition-none" />
                </summary>
                <ul className="mt-1.5 space-y-1.5">
                  {group.items.map((item) => {
                    const sourceTitle = matches
                      .find((match) => match.insight.id === item.insight_id)
                      ?.insight.supporting_findings.find((finding) => finding.url === item.url)
                      ?.title;
                    return (
                      <li key={item.source_id} className="rounded-md bg-muted/35 px-3 py-2">
                        <a href={item.url} target="_blank" rel="noreferrer" className="font-medium text-foreground/80 hover:underline">
                          {sourceTitle || "Cited source"}
                        </a>
                        <p className="mt-0.5 leading-relaxed">{item.reason}</p>
                      </li>
                    );
                  })}
                </ul>
              </details>
            ))}
        </div>
      )}

      {conformity.benchmark_count > 0 && (
        <p className="mt-1.5 text-[10px] text-muted-foreground/70">
          The observed share is a literal count within the admitted cohort, not a probability or confidence interval.
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
              const sourceFinding = sourceInsight?.supporting_findings.find(
                (finding) => finding.url === measurement.url,
              );
              return (
                <li key={`${measurement.url}-${index}`} className="py-2 text-xs text-muted-foreground first:pt-1">
                  <div className="flex items-baseline gap-2">
                    <a href={measurement.url} target="_blank" rel="noreferrer" className="min-w-0 flex-1 truncate hover:text-foreground hover:underline">
                      {sourceFinding?.title || measurement.source_record_id || "Cited source"}
                    </a>
                    <span className="shrink-0 text-[11px] text-muted-foreground/60">
                      {formatNumericExpression(measurement.expression)} · {measurement.age_months != null ? `${Math.round(measurement.age_months)}mo` : "date unknown"}
                    </span>
                  </div>
                  <blockquote className="mt-1 border-l border-border pl-2 text-[11px] leading-relaxed text-foreground/80">
                    {measurement.source_quote}
                  </blockquote>
                  <p className="mt-1 text-[10px] text-muted-foreground/70">
                    {measurement.inclusion_reason} Identity: {measurement.source_identity_status.replace("_", " ")}.
                  </p>
                  <details className="group/semantic mt-1 text-[10px] text-muted-foreground/70">
                    <summary className="inline-flex cursor-pointer select-none items-center gap-1 rounded px-1 py-0.5 outline-none transition-colors hover:bg-muted hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/20 [&::-webkit-details-marker]:hidden motion-reduce:transition-none">
                      Semantic mapping
                      <ChevronDown className="h-2.5 w-2.5 transition-transform group-open/semantic:rotate-180 motion-reduce:transition-none" />
                    </summary>
                    <ul className="mt-1 space-y-0.5 pl-3">
                      <li>Status: {measurement.semantic_status.replace("_", " ")} — {measurement.semantic_reason}</li>
                      <li>Expression: {measurement.expression.kind.replaceAll("_", " ")}</li>
                      {Object.entries(measurement.semantic_assessment.dimensions)
                        .filter(([, dimension]) => dimension.source.state === "specified" || dimension.source.state === "other")
                        .map(([field, dimension]) => (
                          <li key={field}>
                            {field.replace("_", " ")}: {dimension.source.state === "specified" ? dimension.source.value : dimension.source.other}
                          </li>
                        ))}
                    </ul>
                  </details>
                  {sourceInsight && <p className="mt-0.5 line-clamp-1 text-[10px] text-muted-foreground/60">Insight: {sourceInsight.statement}</p>}
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {otherExcluded.length > 0 && (
        <details className="group/excluded mt-3 border-t border-border/70 pt-3">
          <summary className="inline-flex cursor-pointer select-none items-center gap-1.5 rounded-md px-1.5 py-1 text-[11px] font-medium text-muted-foreground outline-none transition-colors hover:bg-muted hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/20 [&::-webkit-details-marker]:hidden motion-reduce:transition-none">
            {otherExcluded.length} measurement{otherExcluded.length === 1 ? "" : "s"} not admitted
            <ChevronDown className="h-3 w-3 transition-transform group-open/excluded:rotate-180 motion-reduce:transition-none" />
          </summary>
          <ul className="mt-2 space-y-2">
            {otherExcluded.map((measurement, index) => (
              <li key={`${measurement.url}-excluded-${index}`} className="rounded-md bg-muted/40 px-3 py-2 text-[11px] text-muted-foreground">
                <div className="flex justify-between gap-3">
                  <a href={measurement.url} target="_blank" rel="noreferrer" className="truncate hover:text-foreground hover:underline">
                    {measurement.source_record_id}
                  </a>
                  <span>{formatNumericExpression(measurement.expression)}</span>
                </div>
                <p className="mt-1 text-foreground/75">“{measurement.source_quote}”</p>
                <p className="mt-1">{measurement.semantic_status}: {measurement.semantic_reason}</p>
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
            <DocumentSourceTrace blockIds={match.doc_block_ids} />
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

/**
 * Scout's own configuration rail: the shared context and document-type fields,
 * plus the retrieval window only this tool can act on.
 *
 * Composed here rather than added to `ConfigurationFields`, which Inspector also
 * renders — the same reason Aligner composes the primitives itself.
 */
function ScoutConfiguration({
  publishedSince,
  onPublishedSinceChange,
}: {
  publishedSince: string;
  onPublishedSinceChange: (value: string) => void;
}) {
  const setHeader = useHeaderStore((state) => state.setHeader);
  const sourceType = useHeaderStore((state) => state.header.source_type);
  return (
    <ConfigurationShell>
      <ContextFields />
      <ConfigFieldGrid className="mt-4">
        <SourceTypeField
          value={sourceType}
          onChange={(value) => setHeader({ source_type: value })}
        />
        <ConfigField label="Published since (optional)">
          <ConfigDateInput
            value={publishedSince}
            onChange={onPublishedSinceChange}
            max={new Date().toISOString().slice(0, 10)}
          />
          <p className="mt-1.5 text-[11px] leading-relaxed text-muted-foreground">
            Only evidence published on or after this date enters the run. Anything
            older is dropped, so no count or benchmark includes it. Sources that
            publish no date, such as web pages, are still included.
          </p>
        </ConfigField>
      </ConfigFieldGrid>
    </ConfigurationShell>
  );
}
