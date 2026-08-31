"use client";

import { useTraceFocus } from "@/lib/trace-focus";
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
} from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { ErrorMessage } from "@/components/ui/error-message";
import { DisclosureRow } from "@/components/ui/disclosure-row";
import { MetricsRow } from "@/components/ui/metrics-row";
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
import { ResultLayout } from "@/components/ui/result-layout";
import {
  ResultToolbar,
  ResultToolbarEnd,
} from "@/components/ui/result-toolbar";
import { ResultSearch } from "@/components/ui/result-search";
import { EXPANDABLE_ROW } from "@/lib/expandable-row";
import { EmptyState } from "@/components/empty-state";
import { SignalChip } from "@/components/ui/signal-chip";
import { CollapsibleCard } from "@/components/collapsible-card";
import { FinalResultActions } from "@/components/final-result-actions";
import {
  continueScout,
  runScout,
  type Conformity,
  type DevelopmentProgram,
  type FunnelStats,
  type EvidenceAssessment,
  type Finding,
  type Header,
  type Match,
  type Measurement,
  type QuantitativeStatementDisposition,
  type Variable,
  type NumericExpression,
  type QuantitativeSemanticProfile,
  type QuantitativeTarget,
  type SemanticSlot,
  type ScoutResponse,
  type SearchTrace,
  type SafetyObservation,
  type SourceRole,
  type TargetRelationship,
  type PrecedentSignal,
  type DocumentSpan,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
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
  runScope,
  pendingQuantitativeReviewCount,
  splitResultContext,
  scoutResultFilename,
  unpackScoutResult,
  readResultIdentity,
} from "@/lib/result-file";
import {
  CALIBRATION_BASIS_LABEL,
  DISPOSITION_LABEL,
  GROUNDING_LABEL,
  OUTCOME_LABEL,
  PRECEDENT_LABEL,
  RELATIONSHIP_LABEL,
  SEMANTIC_STATUS_LABEL,
  TARGET_ROLE_LABEL,
  displayAttributeLabel,
  displayRecordTypeLabel,
  queryTrackLabel,
  sourceDisplayLabel,
  GROUNDING_TONE,
  RELATIONSHIP_TONE,
  OUTCOME_TONE,
} from "@/lib/scout-labels";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ScoutDocumentTrace } from "@/components/scout-document-trace";
import { ScoutSignalHelp } from "@/components/scout-signal-help";
import {
  Computed,
  InterfaceNote,
  Quoted,
  Reading,
} from "@/components/ui/evidence-text";
import { SourceAttributions } from "@/components/source-attributions";
import { ComparatorDistributionPlot } from "@/components/comparator-distribution-plot";
import { EvidenceProvenance } from "@/components/evidence-provenance";
import { FieldSearches } from "@/components/field-searches";
import { ExcludedMeasurements } from "@/components/excluded-measurements";
import { ComparatorCohort } from "@/components/comparator-cohort";
import { Skeleton } from "@/components/ui/skeleton";
import { RELATION_ORDER, sortMatchesForReading } from "@/lib/scout-match-order";
import {
  calibrationView,
  citation,
  documentTargetRows,
  formatMeasure,
  formatMeasurePair,
  insightRegistry,
  needsFindingFallback,
  relationGroups,
  runHeadline,
  type Citation,
  type InsightRegistry,
  type RunHeadline,
  type TargetRow,
} from "@/lib/scout-result-view";
import {
  SCOUT_EMPTY_MESSAGE,
  SCOUT_ORDER_NOTE,
  selectScoutPriorities,
} from "@/lib/scout-priorities";
import { PriorityPanel } from "@/components/ui/priority-panel";
import { DISPLAY_HEADING, EYEBROW } from "@/lib/typography";
import { cn } from "@/lib/utils";
import {
  ARRIVAL_HIGHLIGHT,
  ARRIVAL_HIGHLIGHT_MS,
  DISCLOSURE_MOTION,
  SURFACE_ENTRY_MOTION,
} from "@/lib/motion";
import { SURFACE } from "@/lib/surface";
import { TONE_TEXT, type Tone } from "@/lib/tone";
import { ToneDot } from "@/components/ui/tone-dot";
import {
  applyEvidenceReviewRecommendations,
  evidenceReviewRecommendationSummary,
  reviewQuantitativeCandidateGroup,
} from "@/lib/quantitative-review";
import {
  DocumentSourceProvider,
  DocumentSourceTrace,
} from "@/components/document-source-trace";
import {
  filterProjectionsByRelationship,
  groupProjectionsByRelationship,
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
      <div
        className="h-[560px] space-y-3 p-5"
        role="status"
        aria-label="Preparing evidence map"
      >
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

/**
 * Grounding, strongest first, with the fields nobody could ground last.
 *
 * `EvidenceStrength` is a closed vocabulary but an unordered one, and a distribution read
 * left to right wants an order. Strongest first so the row opens with what held up; "no
 * target stated" ends it because it is the one bucket that is not a verdict on evidence.
 */
const GROUNDING_ORDER = [
  "well_grounded",
  "partial",
  "thin",
  "unsupported",
  "unknown",
  "not_stated",
] as const;

function formatNumericExpression(expression: NumericExpression): string {
  const unit = expression.unit ?? "";
  if (
    expression.kind === "range" ||
    expression.kind === "confidence_interval"
  ) {
    return expression.lower == null || expression.upper == null
      ? "Unresolved numeric expression"
      : `${expression.lower}–${formatMeasure(expression.upper, unit)}`;
  }
  if (expression.value == null) return "Unresolved numeric expression";
  return `${expression.comparator} ${formatMeasure(expression.value, unit)}`;
}

function formatAttributeRefs(
  attributeRefs: string[],
  fallback: string,
): string {
  const labels = Array.from(new Set(attributeRefs)).map(displayAttributeLabel);
  return labels.length > 0 ? labels.join(" · ") : fallback;
}

function formatFieldLinks(
  fieldLinks: QuantitativeTarget["field_links"],
): string {
  return formatAttributeRefs(
    fieldLinks.map((link) => link.attribute_ref),
    "Document claim",
  );
}

function precedentView(signal: PrecedentSignal) {
  return {
    coverage: PRECEDENT_LABEL[signal.precedent],
    outcome: OUTCOME_LABEL[signal.outcome],
    tone: OUTCOME_TONE[signal.outcome],
  };
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
  return (
    RELATION_ORDERED_KEYS.find((relation) =>
      matches.some((match) => match.relation === relation),
    ) ?? "unrelated"
  );
}

// ---------------------------------------------------------------------------
// Shared primitives
// ---------------------------------------------------------------------------

/** Compact value marker used inside expanded detail sections. */

function SignalSummary({
  label,
  value,
  detail,
}: {
  label: string;
  value: string;
  detail?: string;
}) {
  return (
    <div className="min-w-0">
      <p className="text-[11px] font-medium text-muted-foreground">{label}</p>
      <div className="mt-0.5 flex min-w-0 items-center gap-1.5 text-xs">
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

/**
 * A target's role, as a pill.
 *
 * Both review screens showed one and both wrote the shell out by hand. Identical today, which
 * is the state two copies are in right before one of them changes.
 */
function RolePill({ role }: { role: string }) {
  return (
    <span className="rounded-full border border-border px-2 py-0.5 text-[11px] font-medium capitalize text-muted-foreground">
      {role}
    </span>
  );
}

/**
 * A section heading.
 *
 * Deliberately with no help affordance. The four result axes are told apart by contrast,
 * so a tooltip on one of them cannot do the job: it says what Grounding is without saying
 * how it differs from Relation to document target, which is the thing a reader gets wrong.
 * The toolbar's "How to read" shows all four together, and that is the only place they are
 * explained. Twenty-eight fields times four headings was also 112 affordances glossing the
 * same four sentences.
 */
function SectionLabel({ children }: { children: React.ReactNode }) {
  return <p className={EYEBROW}>{children}</p>;
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
        const sourceLabels = (
          f.source_lanes?.length ? f.source_lanes : [f.source]
        ).map((lane) => sourceDisplayLabel(lane, f.source_labels));
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
            <span className="shrink-0 text-[11px] text-muted-foreground">
              {meta}
            </span>
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
      <PageHeader
        title="Scout"
        description="One document’s targets against external evidence: whether its numbers hold up against comparable measurements and development precedent. Feasibility, not completeness — it never checks a document against a template or against another document."
      />
      <HeaderGuard>
        {(header, ready) => (
          <ScoutView header={header as Header} ready={ready} />
        )}
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

  // Covers arriving with a hash already set, or the back button. The click itself is handled
  // on the link, because clicking a citation whose hash is already current fires no
  // `hashchange` and would otherwise do nothing the second time.
  useEffect(() => {
    const openFromHash = () => revealInsight(window.location.hash.slice(1));
    openFromHash();
    window.addEventListener("hashchange", openFromHash);
    return () => window.removeEventListener("hashchange", openFromHash);
  }, []);

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
      if (
        !parsed ||
        !Array.isArray(parsed.variables) ||
        !Array.isArray(parsed.matches)
      ) {
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

  function handleTargetDecision(
    targetId: string,
    decision: "approved" | "rejected",
  ) {
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
            : review,
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
    const previousScore = result.conformity.find(
      (score) => score.target_id === targetId,
    );
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
        score.target_id === targetId ? reviewedScore : score,
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
    if (conformity.every((score, index) => score === result.conformity[index]))
      return;
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
      setError(
        "Resolve every quantitative review candidate before finalizing.",
      );
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
      {result &&
        result.phase === "evidence_review" &&
        ["reviewing", "ready"].includes(reviewStatus) && (
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
        <FieldGrid
          result={result}
          onNewAnalysis={() => setShowRunPanel(true)}
        />
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
  onTargetDecision: (
    targetId: string,
    decision: "approved" | "rejected",
  ) => void;
  onStatementDecision: (unitId: string) => void;
  onAcceptRecommendations: () => void;
  onContinue: () => void;
  onNewAnalysis: () => void;
}) {
  const targets = result.quantitative_ledger.targets;
  const statements = result.quantitative_ledger.reviews.filter(
    (review) =>
      review.classification === "uncertain" ||
      review.classification === "partial_target",
  );
  const pendingTargets = targets.filter(
    (target) => target.review_status === "needs_review",
  );
  const pendingStatements = statements.filter(
    (review) => review.review_status === "needs_review",
  );
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
      : (itemKeys[0] ?? null);

  useEffect(() => {
    if (selectedItem && itemKeys.includes(selectedItem)) return;
    setSelectedItem(firstPendingKey);
  }, [firstPendingKey, itemKeys, selectedItem]);

  const target = selectedItem?.startsWith("target:")
    ? targets.find((item) => item.id === selectedItem.slice("target:".length))
    : undefined;
  const statement = selectedItem?.startsWith("statement:")
    ? statements.find(
        (item) => item.unit_id === selectedItem.slice("statement:".length),
      )
    : undefined;
  const linkedVariables = target
    ? target.field_links.flatMap((link) => {
        const variable = result.variables.find(
          (item) => item.name === link.attribute_ref,
        );
        return variable ? [{ link, variable }] : [];
      })
    : [];
  const confirmedCount = targets.filter(
    (item) => item.review_status === "approved",
  ).length;
  const excludedCount =
    targets.filter((item) => item.review_status === "rejected").length +
    statements.filter((item) => item.review_status === "accepted_exclusion")
      .length;
  const flaggedCount = pendingTargets.length + pendingStatements.length;
  const recommendedTargetCount = pendingTargets.filter(
    (item) =>
      item.ai_recommendation === "confirm" ||
      item.ai_recommendation === "exclude",
  ).length;
  const confirmRecommendationCount = pendingTargets.filter(
    (item) => item.ai_recommendation === "confirm",
  ).length;
  const excludeRecommendationCount = pendingTargets.filter(
    (item) => item.ai_recommendation === "exclude",
  ).length;
  const manualTargetCount =
    pendingTargets.length - recommendedTargetCount + pendingStatements.length;

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
    if (target?.review_status === "needs_review")
      setSelectedItem(nextPendingKey(key));
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
          "overflow-hidden rounded-xl border border-border/60 bg-card shadow-sm",
          SURFACE_ENTRY_MOTION,
        )}
      >
        <ReviewCheckpointHeader
          eyebrow="Target review"
          title="Review document targets"
          description="Confirm that each proposed number is a real document commitment, not background context, an example, or a rejected alternative."
          help={
            <>
              Scout has tied each item to a canonical document field and exact
              source passage. Confirm measurable targets before they shape
              retrieval and statistics. Excluded items remain in the audit
              ledger.
            </>
          }
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
              <Button
                variant="ghost"
                size="sm"
                disabled={busy}
                onClick={onNewAnalysis}
              >
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
                  <ReviewCount
                    tone="success"
                    label={`${confirmRecommendationCount} confirm recommended`}
                  />
                  <ReviewCount
                    tone="neutral"
                    label={`${excludeRecommendationCount} exclude recommended`}
                  />
                  <ReviewCount
                    tone="warning"
                    label={`${manualTargetCount} needs review`}
                  />
                </>
              ) : (
                <>
                  <ReviewCount
                    tone="success"
                    label={`${confirmedCount} confirmed`}
                  />
                  <ReviewCount
                    tone="neutral"
                    label={`${excludedCount} excluded`}
                  />
                </>
              )}
            </>
          }
          actions={
            recommendedTargetCount > 0 ? (
              <Button size="sm" onClick={onAcceptRecommendations}>
                Accept {recommendedTargetCount} AI recommendations
              </Button>
            ) : undefined
          }
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
                detail={
                  item.ai_review_reason ||
                  "No reviewer explanation was returned; manual review is required."
                }
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
                title={formatAttributeRefs(
                  item.attribute_refs,
                  "Document context",
                )}
                subtitle={
                  item.classification === "partial_target"
                    ? "Partially resolved extraction"
                    : "Unresolved extraction"
                }
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
                <Quoted size="prominent">{target.quote}</Quoted>
              </>
            }
            right={
              <>
                <SectionLabel>Proposed measurable target</SectionLabel>
                <div className="mt-3 flex flex-wrap items-baseline gap-x-3 gap-y-1">
                  <p className="text-xl font-semibold text-foreground">
                    {formatNumericExpression(target.expression)}
                  </p>
                  <RolePill role={target.role} />
                </div>
                <dl className="mt-5 grid gap-x-5 gap-y-4 sm:grid-cols-2">
                  {comparisonDimensions(target).map((dimension) => (
                    <div key={dimension} className="min-w-0">
                      <dt className={EYEBROW}>{dimensionLabel(dimension)}</dt>
                      <dd className="mt-0.5 text-xs leading-relaxed text-foreground">
                        {semanticSlotLabel(target.semantic_profile[dimension])}
                      </dd>
                      <dd className="mt-1 text-[11px] leading-relaxed text-muted-foreground">
                        {comparisonRuleLabel(
                          target.comparison_contract[dimension],
                        )}
                      </dd>
                    </div>
                  ))}
                </dl>
                <div className="mt-5 border-t border-border/60 pt-4">
                  <SectionLabel>Linked product fields</SectionLabel>
                  <div className="mt-2 space-y-2">
                    {linkedVariables.map(({ link, variable }) => (
                      <div
                        key={`${link.attribute_ref}:${link.relation}`}
                        className="text-[11px] leading-relaxed"
                      >
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
                  label={
                    aiRecommendationPresentation(target.ai_recommendation).label
                  }
                  tone={
                    aiRecommendationPresentation(target.ai_recommendation).tone
                  }
                >
                  {target.ai_review_reason ||
                    "No explanation was returned; review this proposal manually."}
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
                spans={[
                  { quote: statement.quote, block_ids: [statement.block_id] },
                ]}
              />
            </div>
            <p className="mt-3 text-sm font-semibold text-foreground">
              {formatAttributeRefs(
                statement.attribute_refs,
                "Document context",
              )}
            </p>
            <Quoted size="prominent" className="max-w-4xl">
              {statement.quote}
            </Quoted>
            <InterfaceNote className="mt-4 flex max-w-4xl items-start gap-2">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              <span>{statementReviewReason(statement.reason)}</span>
            </InterfaceNote>
          </div>
        ) : (
          <div className="px-5 py-9 sm:px-7">
            <p className="text-base font-semibold text-foreground">
              Document targets are resolved
            </p>
            <SectionDescription>
              Approved targets will shape target-specific queries and
              quantitative calibration. Rejected and uncertain statements remain
              traceable but cannot enter calculations.
            </SectionDescription>
          </div>
        )}

        <footer className="flex flex-col-reverse gap-2 border-t border-border/60 bg-foreground/[0.045] px-5 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-7">
          <p className="text-[11px] leading-relaxed text-muted-foreground">
            {busy
              ? `${stage ? (SCOUT_STEPS.find((item) => item.key === stage)?.label ?? stage) : "Continuing analysis"}${progress ? ` · ${progress.completed}/${progress.total}` : ""}`
              : "Every decision is stored in the portable draft; no hidden server state is used."}
          </p>
          <div className="flex gap-2">
            {target && (
              <>
                <Button
                  variant="outline"
                  disabled={busy}
                  onClick={() => decideTarget(target.id, "rejected")}
                >
                  Exclude as context
                </Button>
                <Button
                  disabled={busy}
                  onClick={() => decideTarget(target.id, "approved")}
                >
                  Confirm target
                </Button>
              </>
            )}
            {statement && (
              <Button
                disabled={busy}
                onClick={() => decideStatement(statement.unit_id)}
              >
                {statement.classification === "partial_target"
                  ? "Acknowledge unresolved remainder"
                  : "Acknowledge exclusion"}
              </Button>
            )}
            {!target &&
              !statement &&
              pendingTargets.length + pendingStatements.length === 0 && (
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

function ReviewCount({ tone, label }: { tone: Tone; label: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <ToneDot tone={tone} />
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
    <header className="border-b border-border/60 px-5 py-5 sm:px-7">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="flex items-center gap-1.5">
            <p className={EYEBROW}>{eyebrow}</p>
            <ReviewHelp>{help}</ReviewHelp>
          </div>
          <h2 className={cn(DISPLAY_HEADING, "mt-1 text-lg font-semibold text-foreground")}>
            {title}
          </h2>
          <SectionDescription>{description}</SectionDescription>
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
    <div className="border-b border-border/60 bg-foreground/[0.045] px-5 py-5 sm:px-7">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold text-foreground">
              Review overview
            </h3>
            <span className="rounded-full border border-border bg-card px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
              AI prefilled
            </span>
          </div>
          <SectionDescription>{description}</SectionDescription>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex flex-wrap items-center gap-3 text-[11px] font-medium text-muted-foreground">
            {counts}
          </div>
          {actions}
        </div>
      </div>
      <div className="mt-4 max-h-72 overflow-y-auto rounded-lg border border-border/60 bg-card">
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
    positive:
      "border-[hsl(var(--tone-success))]/25 bg-[hsl(var(--tone-success))]/[0.06] text-[hsl(var(--tone-success))]",
    neutral: "border-border bg-foreground/[0.045] text-muted-foreground",
    warning:
      "border-[hsl(var(--tone-warning))]/25 bg-[hsl(var(--tone-warning))]/[0.06] text-[hsl(var(--tone-warning))]",
  }[tone];
  return (
    <button
      type="button"
      onClick={onSelect}
      className={`grid w-full gap-2 px-3 py-2.5 text-left transition-colors hover:bg-foreground/[0.045] sm:grid-cols-[minmax(0,0.9fr)_minmax(9rem,0.7fr)_minmax(0,1.4fr)] sm:items-center ${selected ? "bg-foreground/[0.07]" : "bg-card"}`}
      aria-current={selected ? "true" : undefined}
    >
      <span className="min-w-0">
        <span className="block truncate text-[11px] font-medium text-foreground">
          {title}
        </span>
        <span className="mt-0.5 block truncate text-[11px] text-muted-foreground">
          {subtitle}
        </span>
      </span>
      <span
        className={`w-fit rounded-full border px-2 py-0.5 text-[11px] font-medium ${statusClass}`}
      >
        {status}
      </span>
      <span className="min-w-0 truncate text-[11px] text-muted-foreground">
        {detail}
      </span>
    </button>
  );
}

function ReviewDetailColumns({
  left,
  right,
}: {
  left: ReactNode;
  right: ReactNode;
}) {
  return (
    <div className="grid lg:grid-cols-2">
      <div className="min-w-0 border-b border-border/60 p-5 sm:p-7 lg:border-b-0 lg:border-r">
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
    positive: TONE_TEXT.success,
    neutral: "text-muted-foreground",
    warning: TONE_TEXT.warning,
  }[tone];
  return (
    <div className="mt-4 rounded-lg border border-border/60 bg-foreground/[0.045] p-3">
      <p className={cn(EYEBROW, accent)}>AI recommendation · {label}</p>
      <Reading>{children}</Reading>
    </div>
  );
}

/**
 * The sentence under a heading.
 *
 * The interface's own words, so it needs no mode: a literal in the source has no authorship
 * question. It needs one shape, though. Four copies of this existed at two widths and two
 * sizes, so the caveat under the surveillance heading was set differently from the caveat
 * under the review heading for no reason a reader could act on.
 */
function SectionDescription({
  children,
  /** Spacing and clamping only. Tone, size and measure belong here. */
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <p
      className={cn(
        "mt-1 max-w-3xl text-xs leading-relaxed text-muted-foreground",
        className,
      )}
    >
      {children}
    </p>
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
  if (target.review_status === "approved")
    return { label: "Confirmed", tone: "positive" };
  if (target.review_status === "rejected")
    return { label: "Excluded", tone: "neutral" };
  if (target.ai_recommendation === "confirm")
    return { label: "Confirm recommended", tone: "positive" };
  if (target.ai_recommendation === "exclude")
    return { label: "Exclude recommended", tone: "neutral" };
  return { label: "Needs review", tone: "warning" };
}

function aiRecommendationPresentation(
  recommendation: QuantitativeTarget["ai_recommendation"],
): { label: string; tone: ReviewTone } {
  if (recommendation === "confirm")
    return { label: "Confirm", tone: "positive" };
  if (recommendation === "exclude")
    return { label: "Exclude", tone: "neutral" };
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
  const pending = measurements.filter(
    (item) => item.admission_status === "needs_review",
  );
  if (pending.some((item) => item.ai_recommendation === "admit")) {
    return { label: "Admit recommended", tone: "positive" };
  }
  if (
    pending.length > 0 &&
    pending.every((item) => item.ai_recommendation === "reject")
  ) {
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

function comparisonDimensions(
  target: QuantitativeTarget,
): Array<keyof QuantitativeSemanticProfile> {
  return (
    Object.keys(target.comparison_contract) as Array<
      keyof QuantitativeSemanticProfile
    >
  ).filter(
    (dimension) =>
      target.comparison_contract[dimension].mode !== "unconstrained",
  );
}

function comparisonRuleLabel(
  rule:
    | QuantitativeTarget["comparison_contract"][keyof QuantitativeSemanticProfile]
    | undefined,
): string {
  if (!rule) return "Comparison scope unavailable";
  if (rule.mode === "unconstrained") return "Does not control comparison";
  if (rule.mode === "unknown")
    return `Scope needs review${rule.reason ? ` · ${rule.reason}` : ""}`;
  return `${rule.mode === "exact" ? "Exact" : "Compatible"} scope · ${rule.scope}`;
}

function evidenceUnitLabel(measurement: Measurement): string {
  const labels = [
    measurement.evidence_unit.group,
    measurement.evidence_unit.cohort,
  ]
    .map(semanticSlotLabel)
    .filter(
      (label) => !["Not specified", "Not available", "Unknown"].includes(label),
    );
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
  const allCandidates = result.conformity
    .flatMap((score) =>
      [...score.measurements, ...score.excluded_measurements].map(
        (measurement) => ({
          score,
          measurement,
        }),
      ),
    )
    .filter(
      ({ measurement }) =>
        measurement.evidence_mode === "prose" &&
        ["needs_review", "approved", "rejected"].includes(
          measurement.admission_status,
        ),
    );
  const grouped = new Map<string, typeof allCandidates>();
  for (const item of allCandidates) {
    const unitId =
      item.measurement.evidence_unit_id || item.measurement.source_record_id;
    const key = `${item.score.target_id}::${unitId}`;
    grouped.set(key, [...(grouped.get(key) ?? []), item]);
  }
  const groups = Array.from(grouped.entries());
  const pendingGroups = groups.filter(([, items]) =>
    items.some(
      ({ measurement }) => measurement.admission_status === "needs_review",
    ),
  );
  const groupKeys = groups.map(([key]) => key);
  const firstPendingGroupKey = pendingGroups[0]?.[0] ?? groupKeys[0] ?? null;
  const [selectedGroupKey, setSelectedGroupKey] = useState<string | null>(null);
  useEffect(() => {
    if (selectedGroupKey && groupKeys.includes(selectedGroupKey)) return;
    setSelectedGroupKey(firstPendingGroupKey);
  }, [firstPendingGroupKey, groupKeys, selectedGroupKey]);
  const current =
    groups.find(([key]) => key === selectedGroupKey) ??
    pendingGroups[0] ??
    groups[0];
  const recommendedCandidateId =
    current?.[1].find(
      ({ measurement }) =>
        measurement.admission_status === "needs_review" &&
        measurement.ai_recommendation === "admit",
    )?.measurement.candidate_id ?? null;
  const [selectedCandidateId, setSelectedCandidateId] = useState<string | null>(
    null,
  );
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
    ? (reviewItems.find(
        ({ measurement }) => measurement.candidate_id === selectedCandidateId,
      ) ?? reviewItems[0])
    : reviewItems[0];
  const measurement = activeItem?.measurement;
  const target: QuantitativeTarget | undefined =
    result.quantitative_ledger.targets.find(
      (item) => item.id === score.target_id,
    );
  const dimensions = measurement
    ? ((target
        ? comparisonDimensions(target)
        : Object.keys(measurement.semantic_assessment.dimensions)) as Array<
        keyof typeof measurement.semantic_assessment.dimensions
      >)
    : [];
  const total = groups.length;
  const completed = total - pendingGroups.length;
  const admittedGroupCount = groups.filter(([, items]) =>
    items.some(({ measurement: item }) => item.admission_status === "approved"),
  ).length;
  const rejectedGroupCount = groups.filter(([, items]) =>
    items.every(
      ({ measurement: item }) => item.admission_status === "rejected",
    ),
  ).length;
  const recommendationSummary = evidenceReviewRecommendationSummary(
    result.conformity,
  );
  const actionableRecommendations =
    recommendationSummary.admit + recommendationSummary.reject;

  function sourceFindingFor(item: (typeof allCandidates)[number]) {
    return result.matches
      .find((match) => match.insight.id === item.measurement.insight_id)
      ?.insight.supporting_findings.find(
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
          "overflow-hidden rounded-xl border border-border/60 bg-card shadow-sm",
          SURFACE_ENTRY_MOTION,
        )}
      >
        <ReviewCheckpointHeader
          eyebrow="Evidence review"
          title="Review quantitative evidence"
          description="Decide whether each cited result measures the document target closely enough to enter the comparator statistics."
          help={
            <>
              Admit evidence only when it measures the same outcome, product,
              population, regimen, and time horizon as the document target.
              Rejected evidence remains in the audit trail but cannot enter
              statistics.
            </>
          }
          completed={completed}
          total={total}
          progressLabel="Quantitative evidence review progress"
          actions={
            <>
              {canUndo && (
                <Button variant="ghost" size="sm" onClick={onUndo}>
                  Undo last decision
                </Button>
              )}
              {readyToFinalize && (
                <Button size="sm" onClick={onFinalize}>
                  Finalize result
                </Button>
              )}
              <Button variant="ghost" size="sm" onClick={onNewAnalysis}>
                New analysis
              </Button>
            </>
          }
        />

        <ReviewOverview
          description="Every comparator was mapped to its document target. Select an item to inspect the cited result, dimension mapping, and recommendation before finalizing the evidence set."
          counts={
            <>
              {pendingGroups.length > 0 ? (
                <>
                  <ReviewCount
                    tone="success"
                    label={`${recommendationSummary.admit} admit recommended`}
                  />
                  <ReviewCount
                    tone="neutral"
                    label={`${recommendationSummary.reject} reject recommended`}
                  />
                  <ReviewCount
                    tone="warning"
                    label={`${recommendationSummary.flag} needs review`}
                  />
                </>
              ) : (
                <>
                  <ReviewCount
                    tone="success"
                    label={`${admittedGroupCount} admitted`}
                  />
                  <ReviewCount
                    tone="neutral"
                    label={`${rejectedGroupCount} rejected`}
                  />
                </>
              )}
            </>
          }
          actions={
            actionableRecommendations > 0 ? (
              <Button size="sm" onClick={onAcceptRecommendations}>
                Accept {actionableRecommendations} AI recommendations
              </Button>
            ) : undefined
          }
        >
          {groups.map(([key, items]) => {
            const representative =
              items.find(
                ({ measurement: item }) =>
                  item.admission_status === "needs_review",
              ) ?? items[0];
            const presentation = evidenceReviewPresentation(
              items.map((item) => item.measurement),
            );
            const selected = key === currentGroupKey;
            const sourceTitle =
              sourceFindingFor(representative)?.title ||
              representative.measurement.source_record_id ||
              "Cited source";
            const rowTarget = result.quantitative_ledger.targets.find(
              (item) => item.id === representative.score.target_id,
            );
            return (
              <ReviewListRow
                key={key}
                selected={selected}
                onSelect={() => setSelectedGroupKey(key)}
                title={formatAttributeRefs(
                  representative.score.attribute_refs,
                  "Document claim",
                )}
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
                  spans={
                    score.target_quote && score.doc_block_ids?.length
                      ? [
                          {
                            quote: score.target_quote,
                            block_ids: score.doc_block_ids,
                          },
                        ]
                      : []
                  }
                />
              </div>
              <p className="mt-3 text-base font-semibold text-foreground">
                {formatAttributeRefs(score.attribute_refs, "Document claim")}
              </p>
              <div className="mt-2 flex flex-wrap items-baseline gap-2">
                <span className="text-lg font-semibold text-foreground">
                  {target
                    ? formatNumericExpression(target.expression)
                    : score.target_label}
                </span>
                {target && <RolePill role={target.role} />}
              </div>
              <Quoted size="prominent">{score.target_quote}</Quoted>
            </>
          }
          right={
            <>
              {multiple ? (
                <>
                  <div className="flex items-center gap-1.5">
                    <SectionLabel>Choose one estimate</SectionLabel>
                    <ReviewHelp>
                      These values belong to the same source arm or cohort for
                      this target. Select the one that best represents the
                      target, or choose “None apply.” Distinct non-overlapping
                      arms or cohorts are reviewed separately.
                    </ReviewHelp>
                  </div>
                  <p className="mt-1 text-[11px] text-muted-foreground">
                    Same evidence unit ·{" "}
                    {evidenceUnitLabel(reviewItems[0].measurement)}
                  </p>
                  <div
                    className="mt-3 space-y-2"
                    role="radiogroup"
                    aria-label="Evidence estimate"
                  >
                    {reviewItems.map((item) => {
                      const option = item.measurement;
                      const selected =
                        option.candidate_id === selectedCandidateId;
                      const sourceFinding = sourceFindingFor(item);
                      return (
                        <button
                          key={option.candidate_id}
                          type="button"
                          role="radio"
                          aria-checked={selected}
                          onClick={() =>
                            setSelectedCandidateId(option.candidate_id)
                          }
                          className={`w-full rounded-lg border p-3 text-left transition-colors ${
                            selected
                              ? "border-foreground/45 bg-foreground/[0.07]"
                              : "border-border/60 hover:border-foreground/25 hover:bg-foreground/[0.045]"
                          }`}
                        >
                          <span className="flex items-start gap-3">
                            <span
                              className={`mt-1 h-3.5 w-3.5 shrink-0 rounded-full border ${
                                selected
                                  ? "border-foreground bg-foreground shadow-[inset_0_0_0_3px_hsl(var(--card))]"
                                  : "border-muted-foreground/60"
                              }`}
                            />
                            <span className="min-w-0">
                              <span className="block text-sm font-semibold text-foreground">
                                {formatNumericExpression(option.expression)}
                              </span>
                              <span className="mt-1 line-clamp-3 block text-xs leading-relaxed text-foreground">
                                {option.source_quote}
                              </span>
                              <span className="mt-1.5 block truncate text-[11px] text-muted-foreground">
                                {sourceFinding?.title ||
                                  option.source_record_id ||
                                  "Cited source"}
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
                  <Quoted size="prominent">{measurement.source_quote}</Quoted>
                  <a
                    href={measurement.url}
                    target="_blank"
                    rel="noreferrer"
                    className="mt-3 block truncate text-xs font-medium text-muted-foreground hover:text-foreground hover:underline"
                  >
                    {sourceFindingFor(reviewItems[0])?.title ||
                      measurement.source_record_id ||
                      "Open cited source"}
                  </a>
                </>
              ) : null}
            </>
          }
        />

        <div className="border-t border-border/60 px-5 py-5 sm:px-7">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <SectionLabel>Comparison check</SectionLabel>
            <div className="flex items-center gap-3 text-[11px] text-muted-foreground">
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
          {measurement ? (
            <div className="mt-3 overflow-hidden rounded-lg border border-border/60">
              <div
                className={cn(
                  EYEBROW,
                  "hidden grid-cols-[0.8fr_1fr_1fr_0.65fr] gap-4 bg-foreground/[0.045] px-4 py-2 sm:grid",
                )}
              >
                <span>Dimension</span>
                <span>Target</span>
                <span>Evidence</span>
                <span>Mapping</span>
              </div>
              {dimensions.map((dimension) => {
                const targetSlot = target?.semantic_profile[dimension];
                const comparisonRule = target?.comparison_contract[dimension];
                const mapped =
                  measurement.semantic_assessment.dimensions[dimension];
                const compatibility = mapped?.compatibility.state ?? "unknown";
                return (
                  <div
                    key={dimension}
                    className="grid gap-1 border-t border-border/60 px-4 py-3 first:border-t-0 sm:grid-cols-[0.8fr_1fr_1fr_0.65fr] sm:gap-4"
                  >
                    <span
                      className={cn(
                        EYEBROW,
                        "sm:text-xs sm:normal-case sm:tracking-normal",
                      )}
                    >
                      {dimensionLabel(dimension)}
                    </span>
                    <span className="flex gap-2 text-xs text-foreground">
                      <span className={cn(EYEBROW, "w-16 shrink-0 sm:hidden")}>
                        Target
                      </span>
                      <span>
                        {semanticSlotLabel(targetSlot)}
                        {comparisonRule && (
                          <span className="mt-1 block text-[11px] leading-relaxed text-muted-foreground">
                            {comparisonRuleLabel(comparisonRule)}
                          </span>
                        )}
                      </span>
                    </span>
                    <span className="flex gap-2 text-xs text-foreground">
                      <span className={cn(EYEBROW, "w-16 shrink-0 sm:hidden")}>
                        Evidence
                      </span>
                      {semanticSlotLabel(mapped?.source)}
                    </span>
                    <span className="flex gap-2 text-xs font-medium text-muted-foreground">
                      <span className={cn(EYEBROW, "w-16 shrink-0 sm:hidden")}>
                        Mapping
                      </span>
                      {compatibility === "yes"
                        ? "Aligned"
                        : compatibility === "no"
                          ? "Different"
                          : "Uncertain"}
                    </span>
                  </div>
                );
              })}
            </div>
          ) : (
            <p className="mt-3 rounded-lg border border-dashed border-border px-4 py-5 text-xs text-muted-foreground">
              Select an estimate above to inspect how it maps to the document
              target.
            </p>
          )}
          {measurement && (
            <Reading className="mt-3">{measurement.semantic_reason}</Reading>
          )}
          {measurement && (
            <ReviewRecommendation
              label={
                measurement.ai_recommendation === "admit"
                  ? "Admit"
                  : measurement.ai_recommendation === "reject"
                    ? "Reject"
                    : "Review manually"
              }
              tone={
                measurement.ai_recommendation === "admit"
                  ? "positive"
                  : measurement.ai_recommendation === "reject"
                    ? "neutral"
                    : "warning"
              }
            >
              {measurement.ai_review_reason ||
                "No complete independent recommendation was returned."}
            </ReviewRecommendation>
          )}
        </div>

        <footer className="flex flex-col-reverse gap-2 border-t border-border/60 bg-foreground/[0.045] px-5 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-7">
          <p className="text-[11px] leading-relaxed text-muted-foreground">
            One decision resolves this source evidence unit; its provenance
            remains traceable.
          </p>
          <div className="flex gap-2">
            {pendingItems.length > 0 ? (
              <>
                <Button variant="outline" onClick={() => decideCurrent(null)}>
                  {multiple ? "None apply" : "Reject comparator"}
                </Button>
                <Button
                  disabled={multiple && selectedCandidateId == null}
                  onClick={() =>
                    decideCurrent(
                      multiple
                        ? selectedCandidateId
                        : pendingItems[0].measurement.candidate_id,
                    )
                  }
                >
                  {multiple ? "Use selected estimate" : "Admit comparator"}
                </Button>
              </>
            ) : (
              <span className="self-center text-[11px] font-medium text-muted-foreground">
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
      className="flex items-start gap-2.5 rounded-lg border border-[hsl(var(--tone-warning))]/30 bg-[hsl(var(--tone-warning))]/[0.07] px-3.5 py-3 text-xs text-foreground"
    >
      <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
      <div className="min-w-0">
        <p className="font-medium">Review document context</p>
        {/* The tool's own statement of what it found, then the model's reason for it. They
            were one paragraph, which put a sentence the interface composed and a sentence a
            model wrote in the same voice. */}
        <p className="mt-0.5 leading-relaxed text-muted-foreground">
          {message}
        </p>
        <Reading size="prominent" className="mt-1">
          {validation.reason}
        </Reading>
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
      className="flex items-start gap-2.5 rounded-lg border border-border bg-foreground/[0.045] px-3.5 py-3 text-xs text-foreground"
    >
      <CalendarRange className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" />
      <div className="min-w-0">
        <p className="font-medium">
          Scoped to evidence published since {since}
        </p>
        <p className="mt-0.5 leading-relaxed text-muted-foreground">
          Every count, benchmark, and precedent below describes only that
          window. Sources that publish no date, such as web pages, are included.
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
    for (const f of m.insight.supporting_findings ?? [])
      if (f.url) urls.add(f.url);
  for (const a of result.assessments ?? [])
    for (const f of a.supporting_findings ?? []) if (f.url) urls.add(f.url);
  for (const p of result.precedents ?? [])
    for (const f of p.supporting_findings ?? []) if (f.url) urls.add(f.url);
  for (const c of result.conformity ?? [])
    for (const meas of c.measurements ?? []) if (meas.url) urls.add(meas.url);
  for (const program of result.development_landscape ?? [])
    for (const finding of program.supporting_findings ?? [])
      if (finding.url) urls.add(finding.url);
  for (const observation of result.safety_observations ?? [])
    for (const finding of observation.supporting_findings ?? [])
      if (finding.url) urls.add(finding.url);
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
  const [relationFilter, setRelationFilter] = useState<
    "all" | Match["relation"]
  >("all");
  const [resultTab, setResultTab] = useState("fields");
  const revealTrace = useCallback(() => setResultTab("trace"), []);
  const {
    focus: traceFocus,
    open: openBlockInTrace,
    consume: consumeTraceFocus,
  } = useTraceFocus(revealTrace);
  if (variables.length === 0) {
    return (
      <EmptyState message="No variables were returned for this intervention." />
    );
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
        displayAttributeLabel(a.variable.name).localeCompare(
          displayAttributeLabel(b.variable.name),
        ),
    );

  const headline = runHeadline(rows);
  // The measurable target behind each conformity. `Conformity` carries a pre-joined
  // `target_label` - six semantic slots flattened into one dot-separated run-on - while
  // `QuantitativeTarget.semantic_profile` holds those slots named and separate. The
  // review checkpoint already renders them that way; the result view was reading the
  // flattened copy.
  const targetsById = new Map(
    result.quantitative_ledger.targets.map((target) => [target.id, target]),
  );

  const normalizedQuery = query.trim().toLowerCase();
  const visibleRows = rows.filter((row) => {
    const matchesSearch =
      !normalizedQuery ||
      displayAttributeLabel(row.variable.name)
        .toLowerCase()
        .includes(normalizedQuery) ||
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
        <ResultLayout
          title={runLabel(result, "scout")}
          subtitle={runScope(result, "scout")}
          metrics={
            <RunCoverage
              headline={headline}
              insights={result.stats?.insights ?? 0}
              sources={distinctSourceCount(result)}
            />
          }
          // The two counts have different scopes, and a reader auditing one against the
          // other comes up short: 156 sources are cited only by development and safety
          // records, which have findings but no insights.
          metricsNote="Every field by how well evidence supports its target, so the row sums to the number of fields examined. Precedent and calibration are separate axes and are listed below rather than counted here: a field can carry both, neither, or several, so they partition nothing. Insights are counted within fields; the source count is the whole run, including records that carry no insight."
          tabValue={resultTab}
          onTabChange={setResultTab}
          tabs={
            <>
              <TabsTrigger value="fields">Fields</TabsTrigger>
              {developmentLandscape.length > 0 && (
                <TabsTrigger value="landscape">Landscape</TabsTrigger>
              )}
              {safetyObservations.length > 0 && (
                <TabsTrigger value="safety">Safety</TabsTrigger>
              )}
              <TabsTrigger value="map">Evidence map</TabsTrigger>
              <TabsTrigger value="trace">Documents</TabsTrigger>
            </>
          }
          priorities={{
            // Every item links to a field, so it shows where the fields are.
            tab: "fields",
            panel: (
              <PriorityPanel
                attribution="by Scout"
                items={priorities}
                emptyMessage={SCOUT_EMPTY_MESSAGE}
                orderNote={SCOUT_ORDER_NOTE}
                digest={
                  digest?.state === "ready" ? digest.digest.digest : undefined
                }
                nominations={
                  digest?.state === "ready" ? digest.digest.nominations : []
                }
                digestLoading={digest?.state === "loading"}
                digestError={
                  digest?.state === "failed" ? digest.reason : undefined
                }
              />
            ),
          }}
          footer={
            <SourceAttributions
              findings={resultFindings(result)}
              className="border-t border-border/60 px-5 py-3 sm:px-6"
            />
          }
          actions={
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
          <TabsContent value="fields" className="m-0">
            {(unresolvedFieldCount > 0 ||
              result.quantitative_ledger.status === "uncertain") && (
              <div className="flex items-start gap-2 border-b border-border/60 bg-foreground/[0.045] px-5 py-3 text-xs text-muted-foreground sm:px-6">
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                <div className="space-y-1">
                  {unresolvedFieldCount > 0 && (
                    <div>
                      <p>
                        Document interpretation stopped before retrieval because{" "}
                        {unresolvedFieldCount}{" "}
                        {unresolvedFieldCount === 1 ? "field" : "fields"} could
                        not be bound safely.
                      </p>
                      <details className="mt-1.5">
                        <summary className="cursor-pointer font-medium text-foreground">
                          Review unresolved fields
                        </summary>
                        <ul className="mt-1.5 space-y-1 pl-4">
                          {unresolvedFields.map((variable) => (
                            <li key={variable.name} className="list-disc">
                              <span className="font-medium text-foreground">
                                {displayAttributeLabel(variable.name)}:
                              </span>{" "}
                              {variable.target_resolution_reason ||
                                "No validated decision was returned."}
                            </li>
                          ))}
                        </ul>
                      </details>
                    </div>
                  )}
                  {result.quantitative_ledger.status === "uncertain" && (
                    <p>
                      Some numeric statements remained unresolved after one
                      retry. They were retained for audit and excluded from
                      quantitative calibration; the verified document claims
                      still proceeded through evidence retrieval.
                    </p>
                  )}
                </div>
              </div>
            )}
            <ResultToolbar>
              <ResultSearch
                label="Search fields"
                placeholder="Find a field…"
                value={query}
                onChange={setQuery}
              />
              <Select
                value={relationFilter}
                onValueChange={(value) =>
                  setRelationFilter(value as "all" | Match["relation"])
                }
              >
                <SelectTrigger className="h-8 w-full bg-card sm:w-40">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All relationships</SelectItem>
                  {/* Rendered from the shared vocabulary and its shared order, not typed
                      out again. Four hardcoded labels here meant a filter could go on
                      saying "Supports" after the chips it filters had been renamed. */}
                  {RELATION_ORDERED_KEYS.map((relation) => (
                    <SelectItem key={relation} value={relation}>
                      {RELATIONSHIP_LABEL[relation]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <ResultToolbarEnd
                count={{ shown: visibleRows.length, total: rows.length }}
              >
                {/* The field axis. The records tabs filter on the other one. */}
                <ScoutSignalHelp
                  only={[
                    "relationships",
                    "grounding",
                    "measurable",
                    "precedent",
                  ]}
                />
              </ResultToolbarEnd>
            </ResultToolbar>
            {visibleRows.map((row) => (
              <FieldRow
                key={row.variable.name}
                name={row.variable.name}
                description={row.variable.description}
                matches={row.matches}
                assessment={row.assessment}
                conformities={row.conformities}
                precedent={row.precedent}
                searchPlan={result.search_plan}
                quantitativeTargetStatusReason={
                  row.variable.quantitative_target_status_reason
                }
                targetResolved={row.variable.target_resolved}
                targetResolutionReason={row.variable.target_resolution_reason}
                documentTarget={row.variable.document_target}
                documentSpans={row.variable.document_spans}
                dispositions={row.variable.quantitative_statement_dispositions}
                definitionMode={row.variable.definition_mode}
                evidenceDomain={row.variable.evidence_domain}
                targetsById={targetsById}
              />
            ))}
            {visibleRows.length === 0 && (
              <p className="px-6 py-10 text-center text-sm text-muted-foreground">
                No fields match this view.
              </p>
            )}
          </TabsContent>
          {developmentLandscape.length > 0 && (
            <TabsContent value="landscape" className="m-0">
              <DevelopmentLandscape
                programs={developmentLandscape}
                stats={result.stats}
              />
            </TabsContent>
          )}
          {safetyObservations.length > 0 && (
            <TabsContent value="safety" className="m-0">
              <SafetyObservations observations={safetyObservations} />
            </TabsContent>
          )}
          <TabsContent value="map" className="m-0">
            <ScoutEvidenceMap result={result} />
          </TabsContent>
          <TabsContent value="trace" className="m-0">
            <ScoutDocumentTrace
              result={result}
              focus={traceFocus}
              onFocusConsumed={consumeTraceFocus}
            />
          </TabsContent>
        </ResultLayout>
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
    <ResultToolbar>
      <ResultSearch
        label={searchLabel}
        placeholder={placeholder}
        value={query}
        onChange={onQueryChange}
      />
      <Select
        value={relationship}
        onValueChange={(value) =>
          onRelationshipChange(value as ProjectionRelationshipFilter)
        }
      >
        <SelectTrigger
          // The same words as the tooltip that explains it. This filter is what heads
          // this axis - there is no section label over it - so it is what has to match.
          aria-label="Relation to the uploaded product"
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
      {/* The shared end, not a hand-aligned paragraph. This toolbar was the one of five
          that pushed its count right with its own `sm:ml-auto`, so a change to how a
          toolbar ends would have reached four of them. */}
      <ResultToolbarEnd count={{ shown: visibleCount, total: totalCount }}>
        {/* Only the axis this toolbar filters on. Showing the field topics here put a
            definition of "Unrelated" beside a filter where the word means something
            else - the collision `models.py` names at the vocabulary itself. */}
        <ScoutSignalHelp only={["targetRelationship"]} />
      </ResultToolbarEnd>
    </ResultToolbar>
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
    <InterfaceNote className="mb-3 max-w-4xl">
      Context only. This {kind} concerns{" "}
      {relationship === "analogous"
        ? "an analogous product"
        : "adjacent evidence"}{" "}
      and does not describe the uploaded product.
    </InterfaceNote>
  );
}

/**
 * How many announcements were read, and how many named a program.
 *
 * Stated because the landscape cannot say it. An announcement naming no program leaves no
 * row, so a weak reading and a quiet week produce the same empty view. The pair separates
 * them: "18 announcements read, 4 named a program" is a different fact from "4 read, 4
 * named", and only one of them means the retrieval found little.
 */
function AnnouncementReading({ stats }: { stats?: FunnelStats }) {
  const read = stats?.announcements_read ?? 0;
  if (read === 0) return null;
  const named = stats?.announcements_named ?? 0;
  return (
    <InterfaceNote className="mx-5 mb-4 sm:mx-6">
      <Computed>{read.toLocaleString()}</Computed> announcement
      {read === 1 ? "" : "s"} read,{" "}
      <Computed>{named.toLocaleString()}</Computed> named a program. An
      announcement naming none has no row here.
    </InterfaceNote>
  );
}

function DevelopmentLandscape({
  programs,
  stats,
}: {
  programs: DevelopmentProgram[];
  stats?: FunnelStats;
}) {
  const [query, setQuery] = useState("");
  const [relationship, setRelationship] =
    useState<ProjectionRelationshipFilter>("all");
  const normalizedQuery = query.trim().toLowerCase();
  const relationshipMatches = filterProjectionsByRelationship(
    programs,
    relationship,
  );
  const visible = relationshipMatches.filter(
    (program) =>
      !normalizedQuery ||
      [
        program.name,
        ...program.sponsors,
        ...program.phases,
        ...program.statuses,
      ]
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
      {/* Grouped, not flat. Of 502 records on a real run, 13 were `direct` - and emitted
          in retrieval order those 13 sat anywhere in the list. A count per group is what
          says "13 of these are about your product"; a sorted flat list cannot. Every group
          starts closed: the order and the counts point, the reader opens. */}
      {groupProjectionsByRelationship(visible).map((group) => (
        <details
          key={group.relationship}
          className="group/rel border-b border-border/60 last:border-b-0"
        >
          <summary className="flex cursor-pointer select-none items-center gap-2 px-5 py-2.5 outline-none transition-colors hover:bg-foreground/[0.045] focus-visible:bg-foreground/[0.045] focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring/20 sm:px-6 [&::-webkit-details-marker]:hidden motion-reduce:transition-none">
            <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground transition-transform group-open/rel:rotate-180 motion-reduce:transition-none" />
            <span className="text-xs font-medium text-foreground">
              {relationshipLabel(group.relationship)}
            </span>
            <span className="text-[11px] tabular-nums text-muted-foreground">
              {group.items.length}
            </span>
          </summary>
          <div className={cn("border-t border-border/60", DISCLOSURE_MOTION)}>
            {group.items.map((program) => (
              <details
                key={program.projection_id}
                className="group/expand border-b border-border/60 last:border-b-0"
              >
                <summary className={EXPANDABLE_ROW}>
                  <div className="min-w-0 flex-1">
                    <h3 className="truncate text-sm font-semibold text-foreground">
                      {program.name}
                    </h3>
                    <ProjectionRoleLabels
                      relationship={program.target_relationship}
                      sourceRole={program.source_role}
                    />
                    <div className="mt-2 grid gap-x-6 gap-y-1.5 sm:grid-cols-4">
                      <SignalSummary
                        label="Sponsor"
                        value={program.sponsors.join(" · ") || "—"}
                      />
                      <SignalSummary
                        label="Phase"
                        value={program.phases.join(" · ") || "—"}
                      />
                      <SignalSummary
                        label="Status"
                        value={program.statuses.join(" · ") || "—"}
                      />
                      {/*
                    What the row rests on. Without it, a phase a registry holds and a phase
                    a company announced read identically, and they are not equally
                    checkable.
                  */}
                      <SignalSummary
                        label="From"
                        value={
                          program.record_types
                            .map(displayRecordTypeLabel)
                            .join(" · ") || "—"
                        }
                      />
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-3">
                    <span className="text-[11px] text-muted-foreground">
                      {countLabel(program.supporting_findings.length, "record")}
                    </span>
                    <ChevronDown className="h-4 w-4 text-muted-foreground transition-transform group-open/expand:rotate-180 motion-reduce:transition-none" />
                  </div>
                </summary>
                <div
                  className={cn(
                    "border-t border-border/60 px-5 py-4 sm:px-6",
                    SURFACE.open.body,
                    DISCLOSURE_MOTION,
                  )}
                >
                  <ContextualProjectionNote
                    relationship={program.target_relationship}
                    kind="development record"
                  />
                  {program.target_relationship_reason && (
                    <Reading className="mb-3 mt-0 max-w-4xl">
                      {program.target_relationship_reason}
                    </Reading>
                  )}
                  {program.attribute_refs.length > 0 && (
                    <p className="text-[11px] text-muted-foreground">
                      Retrieved for{" "}
                      {program.attribute_refs
                        .map(displayAttributeLabel)
                        .join(" · ")}
                    </p>
                  )}
                  <SourceList findings={program.supporting_findings} />
                </div>
              </details>
            ))}
          </div>
        </details>
      ))}
      {visible.length === 0 && (
        <p className="px-6 py-10 text-center text-sm text-muted-foreground">
          No development records match this view.
        </p>
      )}
      <AnnouncementReading stats={stats} />
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
  const sections = groupSafetyObservations(observations, {
    query,
    relationship,
  });
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
            className="border-b border-border/60 last:border-b-0"
          >
            <header className="bg-foreground/[0.045] px-5 py-4 sm:px-6">
              <h3
                id={headingId}
                className="text-sm font-semibold text-foreground"
              >
                {section.title}
              </h3>
              <SectionDescription>{section.description}</SectionDescription>
            </header>
            {section.observations.map((observation) => {
              const count = safetyObservationCountLabel(observation);
              return (
                <details
                  key={observation.projection_id}
                  className="group/expand border-t border-border/60"
                >
                  <summary className={EXPANDABLE_ROW}>
                    <div className="min-w-0 flex-1">
                      <p className={EYEBROW}>
                        {safetyRecordTypeLabel(observation.record_type)} ·{" "}
                        {safetySourceSystemLabel(observation.source_system)}
                      </p>
                      <h4 className="mt-1 text-sm font-semibold text-foreground">
                        {observation.product_name}
                      </h4>
                      <Reading size="prominent" className="max-w-4xl">
                        {observation.label}
                      </Reading>
                      <ProjectionRoleLabels
                        relationship={observation.target_relationship}
                        sourceRole={observation.source_role}
                      />
                    </div>
                    <div className="flex shrink-0 items-center gap-3 pt-0.5">
                      {count && (
                        <span className="text-[11px] tabular-nums text-muted-foreground">
                          {count}
                        </span>
                      )}
                      <ChevronDown
                        aria-hidden="true"
                        className="h-4 w-4 text-muted-foreground transition-transform group-open/expand:rotate-180 motion-reduce:transition-none"
                      />
                    </div>
                  </summary>
                  <div
                    className={cn(
                      "border-t border-border/60 px-5 py-4 sm:px-6",
                      SURFACE.open.body,
                    )}
                  >
                    <ContextualProjectionNote
                      relationship={observation.target_relationship}
                      kind="safety observation"
                    />
                    {observation.detail && (
                      <p className="max-w-4xl text-xs leading-relaxed text-foreground">
                        {observation.detail}
                      </p>
                    )}
                    {observation.qualification && (
                      <Reading className="mt-2 max-w-4xl">
                        {observation.qualification}
                      </Reading>
                    )}
                    {observation.target_relationship_reason && (
                      <Reading className="mt-3 max-w-4xl">
                        Relationship: {observation.target_relationship_reason}
                      </Reading>
                    )}
                    {observation.attribute_refs.length > 0 && (
                      <p className="mt-2 text-[11px] text-muted-foreground">
                        Retrieved for{" "}
                        {observation.attribute_refs
                          .map(displayAttributeLabel)
                          .join(" · ")}
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

/**
 * How much of the document was testable, in one line.
 *
 * Deliberately *not* the answer. `PriorityPanel` below owns that - `contradictedTargets`
 * is its first tier, so naming the contradicting fields here said the same thing twice,
 * directly above a panel that says it with the evidence, the reason and a source link.
 *
 * What is left is the part nothing else reports: how many fields stated a target at all,
 * and how many numbers could be calibrated against anything. On a real run 10 of 28 fields
 * stated nothing and 15 of 18 numeric targets had no comparable measurement - which is the
 * difference between "the document holds up" and "most of it could not be checked", and it
 * was previously invisible.
 */
function RunCoverage({
  headline,
  insights,
  sources,
}: {
  headline: RunHeadline;
  /** Insights within fields. Field-bound, unlike the source count beside it. */
  insights: number;
  /** Distinct sources across the whole run, records included. */
  sources: number;
}) {
  return (
    <MetricsRow
      total={headline.fieldCount}
      unit={["field", "fields"]}
      // Grounding, because it is the one axis every field has exactly one of. Precedent
      // and calibration are real signals and they are not distributions: a field can
      // carry both, neither, or several conformities, so counts of them do not partition
      // anything and belong below as facts rather than buckets.
      //
      // Zeros are dropped. A strength nothing fell into is not a fact about the run the
      // way Screener's zero `answered` is - nobody decided it, the shape of the evidence
      // did - and six buckets of which three are zero reads as a wider spread than the
      // run has.
      items={GROUNDING_ORDER.flatMap((strength) => {
        const count = headline.groundingCounts[strength];
        if (count === 0) return [];
        return [{
          label: strength === "not_stated"
            ? "No target stated"
            : GROUNDING_LABEL[strength],
          count,
          tone: strength === "not_stated" ? ("neutral" as const) : GROUNDING_TONE[strength],
        }];
      })}
      // Everything true of the run that is not one field's grounding. Precedent and
      // calibration are real signals and not distributions - a field can carry both,
      // neither, or several conformities - so counts of them partition nothing and are
      // facts rather than buckets.
      //
      // Figures with labels, like the other two tools. This was a paragraph of spans with
      // the numbers emphasised and the words between them not, so `34 numeric targets, 34
      // with no comparable` read as one fact when it is two. How the counts relate is in
      // the note, which is where sentences about figures go.
      facts={[
        { value: insights, label: "insights" },
        { value: sources, label: "sources" },
        ...(headline.numericTargets > 0
          ? [
              {
                value: headline.numericTargets,
                label:
                  headline.numericTargets === 1
                    ? "numeric target"
                    : "numeric targets",
              },
            ]
          : []),
        ...(headline.uncalibratedTargets > 0
          ? [
              {
                value: headline.uncalibratedTargets,
                label: "with no comparable measurement",
              },
            ]
          : []),
        // Counted, not named. An unfavourable precedent is the one signal `PriorityPanel`
        // has no tier for, so the count belongs somewhere - but the field name is right
        // below and one of them renders as "I E Ddi", which helps nobody.
        ...(headline.unfavorableFields.length > 0
          ? [
              {
                value: headline.unfavorableFields.length,
                label: "unfavourable precedent",
              },
            ]
          : []),
        ...(headline.unresolvedCount > 0
          ? [
              {
                value: headline.unresolvedCount,
                label: "interpretation unresolved",
              },
            ]
          : []),
      ]}
    />
  );
}


function FieldRow({
  name,
  description,
  matches,
  assessment,
  conformities,
  precedent,
  searchPlan,
  quantitativeTargetStatusReason,
  targetResolved,
  targetResolutionReason,
  documentTarget,
  documentSpans,
  dispositions,
  definitionMode,
  evidenceDomain,
  targetsById,
}: {
  name: string;
  description: string;
  matches: Match[];
  assessment: EvidenceAssessment | null;
  conformities: Conformity[];
  precedent: PrecedentSignal | null;
  /** The run's whole retrieval record. `FieldSearches` filters it to this field, rather than
   *  the page slicing it 28 times to hand each row its own copy. */
  searchPlan: SearchTrace[] | undefined;
  quantitativeTargetStatusReason: string;
  targetResolved: boolean;
  targetResolutionReason: string;
  documentTarget: string;
  documentSpans: DocumentSpan[];
  /** Numbers the document stated that were not turned into a calibratable target. */
  dispositions: QuantitativeStatementDisposition[];
  definitionMode: Variable["definition_mode"];
  evidenceDomain: Variable["evidence_domain"];
  targetsById: Map<string, QuantitativeTarget>;
}) {
  const evidenceTone = assessment ? GROUNDING_TONE[assessment.strength] : null;
  const precedentMeta = precedent ? precedentView(precedent) : null;
  const counts = relationCounts(matches);
  const comparatorCount = conformities.reduce(
    (total, score) => total + score.benchmark_count,
    0,
  );
  const hasDocumentTarget = Boolean(
    documentTarget.trim() || assessment?.doc_target?.trim(),
  );
  const targetNotStated = targetResolved && !hasDocumentTarget;
  // Built once per field: every signal cites into this instead of re-rendering insights.
  const registry = insightRegistry(matches);
  // `document_spans` reconstructs `document_target` exactly, already split one entry per
  // source table row and each carrying its own blocks. `assessment.doc_target` is only
  // ever a copy of `Variable.document_target` (verified in `evidence_assessor.py`), so
  // rendering the spans shows the same text once, as rows.
  const targetRows = documentTargetRows(documentSpans);
  return (
    <details className="group/expand border-b border-border/60 last:border-b-0">
      <summary className={cn(EXPANDABLE_ROW, "justify-between")}>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2">
            <h3 className="text-sm font-semibold text-foreground">
              {displayAttributeLabel(name)}
            </h3>
          </div>
          {/* The field's own definition, which is project copy rather than anyone's reading
              of this document, so it takes the same shape as the sentence under a section
              heading. Still clamped to one line: a closed row is an index, not a reference. */}
          <SectionDescription className="line-clamp-1">
            {description}
          </SectionDescription>
          {targetNotStated ? (
            <p className="mt-2 text-xs text-muted-foreground">
              Not stated in document · no evidence analysis was run
            </p>
          ) : (
            /* One line of verdicts instead of a four-column grid of label/value/detail.
               A field is read beside 27 others, so what matters is the shape of the row:
               conflicts first because 4 of 911 insights contradict anything, then the two
               standing judgments, then how many numeric targets there are to open. */
            <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1.5">
              {counts.contradicts > 0 && (
                <SignalChip tone={RELATIONSHIP_TONE.contradicts}>
                  {`${RELATIONSHIP_LABEL.contradicts} ${counts.contradicts}`}
                </SignalChip>
              )}
              {counts.confirms > 0 && (
                <SignalChip tone={RELATIONSHIP_TONE.confirms}>
                  {`${RELATIONSHIP_LABEL.confirms} ${counts.confirms}`}
                </SignalChip>
              )}
              {assessment && evidenceTone && (
                <SignalChip tone={evidenceTone}>
                  {GROUNDING_LABEL[assessment.strength]}
                </SignalChip>
              )}
              {precedent && precedentMeta && (
                <SignalChip tone={precedentMeta.tone}>
                  {`${precedentMeta.coverage} · ${precedentMeta.outcome}`}
                </SignalChip>
              )}
              {/* Counts are their own spans, spaced like the chips beside them, rather
                  than one span joined by a middot. The row already spends that glyph on
                  joining the two halves of one signal - `Direct · Mixed` is a single
                  precedent verdict - so using it again between two independent counts
                  made one separator mean two things in one line. Spacing is what
                  separates peers here; the dot is what marks a signal. */}
              {conformities.length > 0 && (
                <span className="text-[11px] tabular-nums text-muted-foreground">
                  {countLabel(conformities.length, "numeric target")}
                </span>
              )}
              {conformities.length > 0 && comparatorCount > 0 && (
                <span className="text-[11px] tabular-nums text-muted-foreground">
                  {countLabel(comparatorCount, "comparator")}
                </span>
              )}
              <span className="text-[11px] tabular-nums text-muted-foreground">
                {countLabel(matches.length, "insight")}
              </span>
            </div>
          )}
        </div>
        <ChevronDown className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground transition-transform group-open/expand:rotate-180 motion-reduce:transition-none" />
      </summary>

      {/* The lighter half of the open row's tint, so the row reads as one block from its
          summary to its last line. Tinting the summary alone marked where an open row began
          and never where it ended. */}
      <div
        className={cn(
          "space-y-4 border-t border-border/60 px-5 py-5 sm:px-6",
          SURFACE.open.body,
          DISCLOSURE_MOTION,
        )}
      >
        {targetNotStated ? (
          <p className="text-xs leading-relaxed text-muted-foreground">
            Not stated in document. Scout did not run evidence analysis for this
            field.
          </p>
        ) : (
          <TargetRows
            rows={targetRows}
            blockIds={assessment?.doc_block_ids ?? []}
          />
        )}
        {!targetResolved && (
          <p className="text-xs leading-relaxed text-muted-foreground">
            <span className="font-medium text-foreground">
              Interpretation unresolved.
            </span>{" "}
            {targetResolutionReason ||
              "No validated document-claim decision was returned."}
          </p>
        )}
        {/* How retrieval was aimed, and the record of it.

            This replaced a line reading "Searched by pulmonary TB (disease) · Clinical
            evidence". Its two halves had different conditions and only one gate. The entity
            was informative on 3 of 28 fields and, measured on a real run, appeared in 4 of
            the 62 searches for its field, so it claimed the aiming of a search it mostly did
            not aim. The evidence domain is true of all 28 fields and was visible on 3,
            because it rode a gate that was not about it.

            `definition_mode` is gone from here too: it is `fixed` on every field of every
            run seen so far, and a dynamic definition now shows itself in the searches. */}
        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
          <p className="text-[11px] text-muted-foreground">
            {dimensionLabel(evidenceDomain)} evidence
            {definitionMode === "dynamic" &&
              " · definition read from the document"}
          </p>
          <FieldSearches
            result={{ search_plan: searchPlan }}
            attributeRef={name}
          />
        </div>
        {/* One section for the numeric targets whether there are any or not. The slot used
            to change shape with its content - a caps heading with rows when targets
            existed, a bold sentence when they did not - so one fact appeared at two
            altitudes. The dispositions nest here rather than sitting beside Grounding and
            Precedent: they explain this section, they are not a fourth assessment. */}
        {!targetNotStated &&
          (conformities.length > 0 || quantitativeTargetStatusReason) && (
            <section className="border-t border-border/60 pt-4">
              <div className="flex flex-wrap items-baseline justify-between gap-x-4">
                {/* Not "Numeric targets", which read as "the numbers among the stated
                  targets" and implied containment. These are a parallel reading of the same
                  document, restricted to the passages a resolved target cites, and what
                  distinguishes them is that evidence can be measured against them. */}
                <SectionLabel>Measurable targets</SectionLabel>
                {/* The count, or nothing. It used to read "none stated" while the sentence
                  directly below it also said there were none, and that sentence says *why*,
                  which a headline cannot. So the two states do not overlap: a number when
                  there are targets, an explanation when there are not. */}
                {conformities.length > 0 && (
                  <span className="text-[11px] tabular-nums text-muted-foreground">
                    {countLabel(conformities.length, "target")}
                  </span>
                )}
              </div>
              {/* All four of these sentences are written where the decision is made, so this is
                the tool accounting for an absence, not a model's view of the field.

                `content`, not a note: this sentence *is* what the section holds when there
                are no measurable targets. Boxed, it was the only bordered element on a card
                of flat prose, so the loudest thing on screen was an absence. */}
              {conformities.length === 0 && quantitativeTargetStatusReason && (
                <InterfaceNote variant="content" className="mt-1">
                  {quantitativeTargetStatusReason}
                </InterfaceNote>
              )}
              {conformities.length > 0 && (
                <>
                  <div className="mt-1 divide-y divide-border/60">
                    {conformities.map((conformity) => (
                      <ConformityBlock
                        key={conformity.target_id}
                        conformity={conformity}
                        matches={matches}
                        target={targetsById.get(conformity.target_id) ?? null}
                      />
                    ))}
                  </div>
                  {/* Once for the section, not once per target. It is a statement about how
                    every comparison here is computed, and a field with seven targets
                    repeated it for each one that had a cohort. */}
                </>
              )}
              {dispositions.length > 0 && (
                <div className="mt-1">
                  <DisclosureRow
                    label="Numbers not used as targets"
                    count={dispositions.length}
                  >
                    <ul className="space-y-3">
                      {dispositions.map((item, index) => (
                        <li key={`${item.disposition}-${index}`}>
                          <p className="text-[11px] font-medium text-foreground">
                            {DISPOSITION_LABEL[item.disposition]}
                          </p>
                          <Quoted>{item.quote}</Quoted>
                          {item.reason && <Reading>{item.reason}</Reading>}
                          <DocumentSourceTrace blockIds={item.block_ids} />
                        </li>
                      ))}
                    </ul>
                  </DisclosureRow>
                </div>
              )}
            </section>
          )}
        {/* The three assessments, grouped. Above this is the subject - what the document
            says. These are judgments *of* it, and six sections separated by one identical
            hairline read as six peers. One heavier rule marks the boundary between the
            claim and the assessment of it; hairlines separate the assessments inside. */}
        {!targetNotStated &&
          (assessment || precedent || matches.length > 0) && (
            <div className="border-t border-border pt-4">
              {assessment && evidenceTone && (
                <SignalVerdict
                  label="Grounding"
                  chips={[
                    {
                      tone: evidenceTone,
                      text: GROUNDING_LABEL[assessment.strength],
                    },
                  ]}
                  reason={assessment.reason}
                  citations={[
                    {
                      cited: citation(
                        assessment.supporting_insight_ids,
                        registry,
                      ),
                    },
                  ]}
                  fallback={assessment.supporting_findings}
                />
              )}
              {precedent && precedentMeta && (
                <SignalVerdict
                  label="Precedent"
                  chips={[
                    { tone: "neutral", text: precedentMeta.coverage },
                    { tone: precedentMeta.tone, text: precedentMeta.outcome },
                  ]}
                  reason={precedent.reason}
                  citations={
                    precedent.coverage_insight_ids?.length ||
                    precedent.outcome_insight_ids?.length
                      ? [
                          {
                            label: "Coverage",
                            cited: citation(
                              precedent.coverage_insight_ids,
                              registry,
                            ),
                          },
                          {
                            label: "Outcome",
                            cited: citation(
                              precedent.outcome_insight_ids,
                              registry,
                            ),
                          },
                        ]
                      : [
                          {
                            cited: citation(
                              precedent.supporting_insight_ids,
                              registry,
                            ),
                          },
                        ]
                  }
                  fallback={precedent.supporting_findings}
                />
              )}
              {!targetNotStated && <InsightGroups registry={registry} />}
            </div>
          )}
      </div>
    </details>
  );
}

/**
 * The target as the document stated it: one row per source table row.
 *
 * This replaced a paragraph. `document_target` is a concatenation of `document_spans`, so
 * four table rows arrived as one 995-character block of `Variable: … Minimum: …
 * Optimistic: …` text with a single citation. The spans were already separated and already
 * block-attributed; rendering them is the same text, readable, cited per row.
 *
 * Minimum and optimistic sit as columns because that is what they are in the source. A row
 * that does not split cleanly is shown whole rather than shown wrong.
 */
function TargetRows({
  rows,
  blockIds,
}: {
  rows: TargetRow[];
  blockIds: string[];
}) {
  if (rows.length === 0) return null;
  const bounded = rows.some((row) => row.kind === "bounded");
  return (
    <section>
      <div className="flex flex-wrap items-baseline justify-between gap-x-4">
        <SectionLabel>Target stated in document</SectionLabel>
        {rows.length === 0 && <DocumentSourceTrace blockIds={blockIds} />}
      </div>
      {bounded && (
        <div className="mt-2 hidden grid-cols-[minmax(0,0.8fr)_minmax(0,1.6fr)_minmax(0,1.6fr)_7rem] gap-x-4 pb-1 sm:grid">
          <span className={EYEBROW}>Variable</span>
          <span className={EYEBROW}>Minimum</span>
          <span className={EYEBROW}>Optimistic</span>
        </div>
      )}
      <div className="divide-y divide-border/60">
        {rows.map((row, index) =>
          row.kind === "bounded" ? (
            <div
              key={index}
              /* A fixed trailing column for the trigger. Sharing the optimistic cell left
                 it fighting the longest text on the row for space, so its label broke across
                 two lines and the row grew taller than its siblings. */
              // `items-start`, so the trigger sits on the row's first line rather than
              // floating in the middle of a cell three lines tall.
              className="grid items-start gap-x-4 gap-y-0.5 py-2 sm:grid-cols-[minmax(0,0.8fr)_minmax(0,1.6fr)_minmax(0,1.6fr)_7rem]"
            >
              <p className="text-xs font-medium text-foreground">
                {row.variable}
              </p>
              <Quoted size="prominent" className="mt-0">
                <span className={cn(EYEBROW, "sm:hidden")}>Minimum </span>
                {row.minimum || "—"}
              </Quoted>
              <Quoted size="prominent" className="mt-0">
                <span className={cn(EYEBROW, "sm:hidden")}>Optimistic </span>
                {row.optimistic || "—"}
              </Quoted>
              {/* Against the right edge, matching the numeric-target rows below, which
                  pack their triggers the same way. */}
              <span className="justify-self-end">
                <DocumentSourceTrace
                  blockIds={row.blockIds}
                  spans={[{ quote: row.quote, block_ids: row.blockIds }]}
                />
              </span>
            </div>
          ) : (
            <div
              key={index}
              className="flex items-start justify-between gap-3 py-2"
            >
              {/* The document's own words, so ruled. It rendered as plain prose here and
                  as a quote in the trace panel that opens from it - the same text, two
                  treatments, one of them saying nothing about where it came from. */}
              <Quoted size="prominent" className="mt-0 min-w-0 flex-1">
                {row.text}
              </Quoted>
              <DocumentSourceTrace
                blockIds={row.blockIds}
                spans={[{ quote: row.quote, block_ids: row.blockIds }]}
              />
            </div>
          ),
        )}
      </div>
    </section>
  );
}

function ConformityBlock({
  conformity,
  matches,
  target,
}: {
  conformity: Conformity;
  matches: Match[];
  /** The measurable target, when the ledger still holds it. Supplies the named semantic
   *  slots that `conformity.target_label` had flattened into one line. */
  target: QuantitativeTarget | null;
}) {
  // The expression alone, not the flattened label: "<= 2 months" rather than 200
  // characters of semantic slots joined by dots. The slots are shown below, named.
  const targetLabel = target
    ? formatNumericExpression(target.expression)
    : `${conformity.comparator} ${formatMeasure(conformity.target_value, conformity.unit)}`;
  const dimensions = target ? comparisonDimensions(target) : [];
  const formatBenchmark = (value: number | null) =>
    formatMeasure(value, conformity.unit);
  const coverageLabel = CALIBRATION_BASIS_LABEL[conformity.calibration_status];
  const targetRoleLabel = TARGET_ROLE_LABEL[conformity.target_role];
  const view = calibrationView(conformity);
  // Three statistics always, the two quartile cells only when they are presentable, and the
  // basis. Counted here so the grid can shape itself to what it holds.
  const statCellCount =
    3 +
    (view.showQuartiles ? 1 : 0) +
    (conformity.ambition_percentile != null && view.showQuartiles ? 1 : 0) +
    1;

  return (
    /* A row that opens, like every other level of this view. It was the last thing that
       expanded its detail unconditionally - quote, two to seven named slots, statistics and
       cohort - so seven targets on one field ran to roughly seventy lines. The header line
       is what a reader scans; the rest is why. */
    <details className="group/target py-3 first:pt-0 last:pb-0">
      <summary className="flex cursor-pointer select-none items-baseline gap-x-3 outline-none focus-visible:ring-2 focus-visible:ring-ring/20 [&::-webkit-details-marker]:hidden">
        <ChevronDown className="h-3.5 w-3.5 shrink-0 self-center text-muted-foreground transition-transform group-open/target:rotate-180 motion-reduce:transition-none" />
        {/* The reading, which flexes and wraps inside its own box. Left in the outer row it
            competed with the triggers for width, so a long outcome pushed them off. */}
        <span className="flex min-w-0 flex-1 flex-wrap items-baseline gap-x-3 gap-y-0.5">
          <span className="text-sm font-medium tabular-nums text-foreground">
            {targetLabel}
          </span>
          <span className="text-[11px] text-muted-foreground">
            {targetRoleLabel}
          </span>
          {/* The verdict, and only the verdict. How many comparators there were is the
              trigger's count, and how many met the target is the Comparators panel's own
              description, so naming either here stated it twice. */}
          <span className="text-xs font-medium text-foreground">
            {view.positionLabel}
          </span>
        </span>
        {/* Packed against the right edge, and shrink-wrapped.

            These used to sit in fixed-width slots that held their space when empty, so a
            target with no comparators showed two columns of nothing. That aligned each
            trigger down this list at the cost of two things: the gaps read as missing data
            rather than as nothing to show, and the same `In document` trigger landed 14rem
            further left here than in the target table above it, which shares this screen.

            Right-packing gives up per-column alignment and keeps the order fixed, so the
            trigger a reader is looking for is still in a predictable position relative to
            its siblings, and every row now ends on the same edge as the table above.

            `self-start`, not centred: on a row whose text wraps to three lines a centred
            trigger floats in the middle, away from the line it belongs to. */}
        <span className="flex shrink-0 items-center justify-end gap-1 self-start">
          <ComparatorCohort conformity={conformity} matches={matches} />
          <ExcludedMeasurements conformity={conformity} matches={matches} />
          {/* Last, so it holds the right edge. Each of these three renders nothing when it
              has nothing, and packing right means only the final position is stable - so it
              belongs to the trigger that is almost always present. It also puts `In
              document` in the same column as the target table above, whose only trigger is
              this one, in its rightmost cell. */}
          <DocumentSourceTrace
            blockIds={conformity.doc_block_ids}
            spans={
              conformity.target_quote && conformity.doc_block_ids?.length
                ? [
                    {
                      quote: conformity.target_quote,
                      block_ids: conformity.doc_block_ids,
                    },
                  ]
                : []
            }
          />
        </span>
      </summary>

      <div className={cn(DISCLOSURE_MOTION)}>
        {conformity.target_quote && (
          <Quoted size="prominent" className="mt-1.5">
            {conformity.target_quote}
          </Quoted>
        )}

        {/* What this number is a measure of, one named slot per line. The same profile the
          review checkpoint shows; only the constrained slots, because an unconstrained
          one places no requirement on a comparator. */}
        {dimensions.length > 0 && target && (
          <dl className="mt-2 grid gap-x-6 gap-y-1 sm:grid-cols-2">
            {dimensions.map((dimension) => (
              <div key={dimension} className="flex min-w-0 gap-2">
                <dt className="shrink-0 text-[11px] text-muted-foreground">
                  {dimensionLabel(dimension)}
                </dt>
                <dd className="min-w-0 text-[11px] text-foreground">
                  {semanticSlotLabel(target.semantic_profile[dimension])}
                </dd>
              </div>
            ))}
          </dl>
        )}
        {/* The fallback when no structured target was resolved: the label the pipeline composed
          for what was scored, e.g. "adult threshold <=1.0 mL". Full contrast, because it
          stands in for the target itself here, not for anyone's reading of it. */}
        {!target && conformity.target_label && (
          <Computed className="mt-2 block text-[11px]">
            {conformity.target_label}
          </Computed>
        )}

        {/* The grid appears at three comparators, where an observed SD exists. Below that it
          was five cells of "Not shown" beside one number - on a real run quartiles were
          presentable for 0 of 12 targets and an SD for 1. */}
        {view.shape === "full" && (
          <>
            {/* Columns follow the cell count, because it is known: four without quartiles, five
              or six with them. At a fixed three, four cells laid out 3 + 1 and the lone cell
              on the second row read as something missing rather than as the fourth of four. */}
            <dl
              className={cn(
                "mt-3 grid grid-cols-2 gap-x-6 gap-y-3",
                statCellCount % 3 === 0
                  ? "sm:grid-cols-3"
                  : statCellCount % 2 === 0
                    ? "sm:grid-cols-2"
                    : "sm:grid-cols-3",
              )}
            >
              <StatCell
                label="External median"
                value={formatBenchmark(conformity.benchmark_median)}
              />
              <StatCell label={view.observedLabel} value={view.observedValue} />
              <StatCell
                label={view.showDeviation ? "Mean · observed SD" : "Mean"}
                value={
                  view.showDeviation
                    ? formatMeasurePair(
                        conformity.benchmark_mean,
                        conformity.benchmark_standard_deviation,
                        conformity.unit,
                        " · ",
                      )
                    : formatBenchmark(conformity.benchmark_mean)
                }
              />
              {view.showQuartiles && (
                <StatCell
                  label="Middle 50%"
                  value={formatMeasurePair(
                    conformity.benchmark_lower_quartile,
                    conformity.benchmark_upper_quartile,
                    conformity.unit,
                    "–",
                  )}
                />
              )}
              {conformity.ambition_percentile != null && view.showQuartiles && (
                <StatCell
                  label="Ambition percentile"
                  value={formatOrdinal(
                    Math.round(conformity.ambition_percentile * 100),
                  )}
                />
              )}
              <StatCell label="Comparator basis" value={coverageLabel} />
            </dl>
          </>
        )}

        <ComparatorDistributionPlot conformity={conformity} matches={matches} />
      </div>
    </details>
  );
}

/**
 * One statistic about the comparator cohort.
 *
 * No rules between cells. They were drawn per cell with `last:border-r-0` and an
 * `nth-last-child(-n+3)` rule for the bottom edge, both of which encode "three columns" in a
 * grid that has two at narrow widths and two or three at wide ones. At two columns the second
 * cell kept a right border with nothing beyond it and lost the bottom border it needed, which
 * is the ragged half-line a reader sees. Any grid whose column count answers to its content
 * recreates that, so the rules go rather than get another selector.
 *
 * Nothing is lost by removing them: the semantic profile directly above is the same shape,
 * two columns of label over value, and has never had rules. The uppercase label is what
 * separates one cell from the next. Dropping the horizontal padding also lines these labels
 * up with that block instead of sitting indented from it.
 */
function StatCell({
  label,
  value,
  detail,
}: {
  label: string;
  value: string;
  detail?: string;
}) {
  return (
    <div className="py-1">
      <dt className={EYEBROW}>{label}</dt>
      <dd className="mt-0.5 text-xs font-medium text-foreground">{value}</dd>
      {detail && (
        <dd className="text-[11px] text-muted-foreground">{detail}</dd>
      )}
    </div>
  );
}

/**
 * One openable group inside a field, in the shape all of them use.
 *
 * Four sections held groups and each drew its own row: the relation buckets had a chevron, a
 * tone dot, a label and a count; the numbers-not-used-as-targets row had a chevron, a label
 * and a count at different spacing; and the two verdicts had no row at all, just a count in
 * loose text. Three ways of saying "this many, here they are", so a reader could not tell
 * that the count beside Grounding and the count beside Conflicts were the same kind of
 * thing.
 *
 * The dot is optional because it carries a relation's tone, and only relations have one.
 * `note` is for the exceptional case a count cannot state on its own.
 */

/**
 * A signal's verdict, its reason, and a pointer to the insights behind it.
 *
 * The pointer is the whole change. `supporting_insight_ids` was already a list of
 * references, and the previous renderer expanded each one into a full copy of the insight
 * and its sources - so an insight cited by grounding, precedent coverage, precedent
 * outcome and the relationship list was drawn five times. On a real 28-field run that was
 * 937 redundant renders, 51% of all insight rendering. Here a signal says how many it
 * rests on and where they are; the insights themselves are drawn once, below.
 */
function SignalVerdict({
  label,
  chips,
  reason,
  citations,
  fallback,
}: {
  label: string;
  chips: { tone: Tone; text: string }[];
  reason: string;
  citations: { label?: string; cited: Citation }[];
  /** Drawn only when nothing the ids named could be found; see `needsFindingFallback`. */
  fallback: Finding[];
}) {
  const orphaned = citations.every((entry) =>
    needsFindingFallback(entry.cited),
  );
  return (
    <section className="border-t border-border/60 pt-4 first:border-t-0 first:pt-0">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <SectionLabel>{label}</SectionLabel>
        <div className="flex items-center gap-3">
          {chips.map((chip) => (
            <SignalChip key={chip.text} tone={chip.tone}>
              {chip.text}
            </SignalChip>
          ))}
        </div>
      </div>
      {/* The model's own sentence, so it reads muted like every other model-authored
          reason in this view. Full contrast is reserved for the tool's own words and the
          document's values, which is the only authorship distinction a reader can act on. */}
      {reason && (
        <Reading size="prominent" className="mt-1.5">
          {reason}
        </Reading>
      )}
      {/* The same row as a relation bucket, so a verdict's evidence opens the way every
          other group in this field opens. A citation naming an insight the field does not
          hold is the one thing a count cannot say on its own, so that alone gets a note. */}
      <div className="mt-1">
        {citations
          .filter((entry) => entry.cited.total > 0)
          .map((entry) => (
            <DisclosureRow
              key={entry.label ?? label}
              // Every row names the question its insights answered, never the material.
              // Precedent's two are "Coverage" and "Outcome"; grounding asks one thing -
              // is this target justified - so its row is "Justification".
              //
              // Not "Evidence", which was true of every row on the screen and so
              // distinguished none of them: coverage insights are evidence, outcome
              // insights are evidence, and so are the relation counts below. Not
              // "Support" either, which collides with `Supports`, the per-insight
              // relation label visible in the same view. And not the bare count: these are
              // all counts of insights, so putting the unit in the label slot would make
              // one row look like a different kind of thing.
              label={entry.label ?? "Justification"}
              count={entry.cited.resolved.length}
              note={
                entry.cited.unresolvedCount > 0
                  ? `of ${entry.cited.total} cited · ${entry.cited.unresolvedCount} not retained`
                  : undefined
              }
            >
              <CitedInsightIndex cited={entry.cited} />
            </DisclosureRow>
          ))}
      </div>
      {orphaned && fallback.length > 0 && <SourceList findings={fallback} />}
    </section>
  );
}

/**
 * Which insights a verdict rests on, not just how many.
 *
 * A count alone could not be checked. "Grounding: 7 insights" above a list of 63 left a
 * reader unable to say *which* 7, and the ids were already resolved to build that number, so
 * the answer was computed and then discarded.
 *
 * An index, deliberately, not a second copy. Each cited insight is one line that links to
 * its full record in the relation buckets below, where it is drawn once with its reason and
 * both directions of provenance. Measured on a real run: grounding cites 177, precedent 451,
 * so drawing them in full would add 628 insight renders to the 911 that exist, which is most
 * of the duplication this view was rebuilt to remove. The relation dot travels with each
 * line, because a verdict's citations span buckets and which bucket it came from is the
 * thing a reader wants next.
 */
function CitedInsightIndex({ cited }: { cited: Citation }) {
  return (
    <ul className="space-y-1 pt-0.5">
      {cited.resolved.map((match, index) => (
        <li key={match.insight.id || index}>
          <a
            href={`#${insightAnchor(match) ?? ""}`}
            onClick={() => revealInsight(insightAnchor(match) ?? "")}
            className="flex items-start gap-2 rounded text-xs leading-relaxed text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/20 motion-reduce:transition-none"
          >
            <ToneDot tone={RELATIONSHIP_TONE[match.relation]} className="mt-1.5" />
            <Reading inline size="prominent" className="min-w-0">
              <span className="sr-only">
                {RELATIONSHIP_LABEL[match.relation]}:{" "}
              </span>
              {match.insight.statement}
            </Reading>
          </a>
        </li>
      ))}
    </ul>
  );
}

/**
 * The one place insights are drawn, grouped by what each does to the claim.
 *
 * Measured on a real run: `extends` 78%, `unrelated` 19%, `confirms` 2%, `contradicts`
 * 0.4%. So the groups are ordered by what settles something, and every one of them starts
 * closed behind its count - nothing opens itself. Ordering says where to look; opening is
 * the reader's. Nothing is removed: every insight is still here, and this is its only copy.
 */
function InsightGroups({ registry }: { registry: InsightRegistry }) {
  const total = registry.groups.reduce(
    (sum, group) => sum + group.matches.length,
    0,
  );
  if (registry.groups.length === 0) {
    return (
      <p className="text-xs text-muted-foreground">
        No outside evidence was classified against this field's target.
      </p>
    );
  }
  return (
    <section className="border-t border-border/60 pt-4 first:border-t-0 first:pt-0">
      {/* Named for the question it answers, like Grounding and Precedent. "External
          evidence" named the material instead, which collided with Grounding (also about
          outside evidence) and read as the pool those verdicts were computed from, so a
          reader asked why the counts did not sum. It is the fourth verdict: one relation per
          insight. The phrase is the one the evidence map already renders for this axis, and
          it says *target* where the projection views say *product*, which is the other axis
          the word could mean. */}
      {/* A headline on the right, like the three sections above it. This was the only one
          with nothing there, so it read as a list of controls rather than as a fourth
          reading of the field. The total, because unlike Grounding this axis has no single
          verdict: it partitions every insight, and the partition is the answer. */}
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <SectionLabel>Relation to document target</SectionLabel>
        <span className="text-[11px] tabular-nums text-muted-foreground">
          {countLabel(total, "insight")}
        </span>
      </div>
      <div className="mt-1">
        {registry.groups.map((group) => (
          <DisclosureRow
            key={group.relation}
            label={RELATIONSHIP_LABEL[group.relation]}
            tone={RELATIONSHIP_TONE[group.relation]}
            count={group.matches.length}
          >
            <ul className="space-y-4">
              {group.matches.map((match, index) => (
                <li
                  key={match.insight.id || index}
                  id={insightAnchor(match)}
                  // Negative margin against the padding, so making room for an inset ring
                  // does not shift the statement when nothing has arrived.
                  className="-mx-2 rounded-md px-2 py-1 transition-shadow duration-base ease-enter motion-reduce:transition-none"
                >
                  {/* The model's sentence, so muted and marked. It was at full contrast,
                      which is the treatment for the tool's own words and the document's
                      values - and it sat directly above `match.reason`, the model's
                      judgement *about* it, which was already muted. Two contrasts told a
                      reader the two lines had different authors when they have one. */}
                  <Reading size="prominent" className="mt-0">
                    {match.insight.statement}
                  </Reading>
                  {/* `continued`, because this is the model's reasoning *about* the
                      sentence above it - one contribution, one level apart. Marked in its
                      own right it read as the next item in a list rather than as a note on
                      the line above. No left rule either: that shape means "quoted
                      verbatim", and the other seven places it appears are a quote. */}
                  {match.reason && <Reading continued>{match.reason}</Reading>}
                  {/* Both directions of provenance, both behind a click and neither
                      expanded by default. Rendering every source inline put 1,121 finding
                      rows on one run in front of the statements they support. */}
                  <div className="mt-1 flex flex-wrap items-center gap-1">
                    <DocumentSourceTrace blockIds={match.doc_block_ids} />
                    <EvidenceProvenance insight={match.insight} />
                  </div>
                </li>
              ))}
            </ul>
          </DisclosureRow>
        ))}
      </div>
    </section>
  );
}

/**
 * Opens an insight that a citation points at, and scrolls to it.
 *
 * A reader following a verdict's citation should land on the open insight, not on a closed
 * row they have to hunt for. Each one is nested twice, in its relation bucket and in its
 * field, so every `<details>` above it has to be opened. Same problem and same approach as
 * the prompt reference, where "read the instructions behind this" landed on a closed row.
 */
let arrivalTimeout: number | undefined;

function revealInsight(id: string): void {
  if (!id.startsWith("insight-")) return;
  const target = document.getElementById(id);
  if (!target) return;
  let ancestor = target.closest("details");
  while (ancestor) {
    ancestor.open = true;
    ancestor = ancestor.parentElement?.closest("details") ?? null;
  }
  const reduceMotion = window.matchMedia(
    "(prefers-reduced-motion: reduce)",
  ).matches;
  target.scrollIntoView({
    behavior: reduceMotion ? "auto" : "smooth",
    block: "center",
  });

  // The same arrival ring the document trace uses, and for the same reason: opening the
  // bucket is not enough, because the insight lands mid-screen among up to 43 others that
  // look exactly like it. The recipe is imported rather than restyled here, so a jump into a
  // field reads like a jump into a passage.
  const marks = ARRIVAL_HIGHLIGHT.split(" ");
  window.clearTimeout(arrivalTimeout);
  document.querySelectorAll("[data-arrived]").forEach((stale) => {
    stale.removeAttribute("data-arrived");
    stale.classList.remove(...marks);
  });
  target.setAttribute("data-arrived", "");
  target.classList.add(...marks);
  arrivalTimeout = window.setTimeout(() => {
    target.removeAttribute("data-arrived");
    target.classList.remove(...marks);
  }, ARRIVAL_HIGHLIGHT_MS);
}

/** Stable anchor so a signal's citation can point at the insight it rests on. */
function insightAnchor(match: Match): string | undefined {
  return match.insight.id ? `insight-${match.insight.id}` : undefined;
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
            Only evidence published on or after this date enters the run, so no
            count or benchmark includes anything older. Sources that can filter
            by date ask for the window directly, which changes what they rank
            rather than only what survives. Sources that publish no date, such
            as web pages, are still included.
          </p>
        </ConfigField>
      </ConfigFieldGrid>
    </ConfigurationShell>
  );
}
