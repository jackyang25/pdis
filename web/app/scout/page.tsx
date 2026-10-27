"use client";
import { formatMeasure, formatMeasurePair } from "@/lib/measure-format";
import { DocumentExtractionNotice } from "@/components/document-extraction-notice";
import { CaveatNotice, ResultNotices, WarningNotice } from "@/components/ui/warning-notice";
import { usePublishReviewContext, type ReviewSelection } from "@/lib/assistant-review-context";

import { useTraceFocus } from "@/lib/trace-focus";
import {
  type CSSProperties,
  memo,
  useCallback,
  useContext,
  useDeferredValue,
  useEffect,
  useId,
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
import { DisclosureRow } from "@/components/ui/disclosure-row";
import { MetricsRow } from "@/components/ui/metrics-row";
import { RunPanel } from "@/components/run-panel";
import { RunHistory } from "@/components/run-history";
import {
  ContextFields,
  SourceTypeField,
} from "@/components/configuration-fields";
import {
  ConfigChip,
  ConfigDateInput,
  ConfigField,
  ConfigHelp,
  ConfigSectionHeading,
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
import { matchesQuery, normalizeQuery } from "@/lib/result-search";
import { EXPANDABLE_ROW } from "@/lib/expandable-row";
import { EmptyState } from "@/components/empty-state";
import { SignalChip } from "@/components/ui/signal-chip";
import { VerdictPill } from "@/components/ui/verdict-pill";
import { FinalResultActions, NewAnalysisButton } from "@/components/final-result-actions";
import {
  continueScout,
  runScout,
  type Conformity,
  type DevelopmentProgram,
  type FunnelStats,
  type EvidenceAssessment,
  type EvidenceStrength,
  type Finding,
  type Header,
  type Match,
  type Measurement,
  type QuantitativeStatementDisposition,
  type Variable,
  type QuantitativeTarget,
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
  PopoverTrigger,
} from "@/components/ui/popover";
import { HelpPopoverContent } from "@/components/ui/help-content";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useScoutSession } from "@/lib/session";
import { importTool, runTool, trackTool } from "@/lib/tool-run";
import { useShallow } from "zustand/react/shallow";
import { usePriorityReading } from "@/lib/priority-reading";
import { toolAuthority } from "@/lib/tools";
import { scoutReviewStatus } from "@/lib/scout-review-session";
import {
  packScoutResult,
  runLabel,
  runScope,
  pendingQuantitativeReviewCount,
  runFilename,
  unpackScoutResult,
} from "@/lib/result-file";
import {
  CALIBRATION_BASIS_LABEL,
  DISPOSITION_LABEL,
  GROUNDING_LABEL,
  OUTCOME_LABEL,
  PRECEDENT_LABEL,
  RELATIONSHIP_LABEL,
  TARGET_ROLE_LABEL,
  displayAttributeLabel,
  displayRecordTypeLabel,
  sourceDisplayLabel,
  statementReviewReason,
  outcomeIsSeparate,
  reviewRecommendationReason,
  verdictNote,
  verdictReason,
  GROUNDING_TONE,
  RELATIONSHIP_TONE,
  OUTCOME_TONE,
} from "@/lib/scout-labels";
import { TabsContent, TabsTrigger } from "@/components/ui/tabs";
import { ScoutDocumentTrace } from "@/components/scout-document-trace";
import { ScoutFieldSummary } from "@/components/scout-field-summary";
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
import { ScoutComparison, TargetQualifierSource, TargetComparisonRules } from "@/components/scout-comparison";
import { semanticSlotLabel, dimensionLabel, comparisonDimensions } from "@/lib/scout-comparison";
import { Skeleton } from "@/components/ui/skeleton";
import { RELATION_ORDER, sortMatchesForReading } from "@/lib/scout-match-order";
import {
  calibrationView,
  citation,
  distinctSourceCount,
  documentTargetRows,
  conformityTargetLabel,
  retrievalScopeParts,
  formatNumericExpression,
  insightRegistry,
  needsFindingFallback,
  runHeadline,
  unassessedChecks,
  unreconciledSets,
  type Citation,
  type InsightRegistry,
  type RunHeadline,
  type ScopePart,
  type TargetRow,
} from "@/lib/scout-result-view";
import {
  SCOUT_PRIORITY_FOCUS,
  scoutPriorityFindings,
} from "@/lib/scout-priorities";
import {
  fieldSelectionSummary,
  searchableFields,
  withEveryFieldSearched,
  withFieldSearched,
} from "@/lib/scout-field-selection";
import { PriorityPanel } from "@/components/ui/priority-panel";
import { DISPLAY_HEADING, EYEBROW, ROW_TITLE } from "@/lib/typography";
import { cn } from "@/lib/utils";
import {
  ARRIVAL_HIGHLIGHT,
  ARRIVAL_HIGHLIGHT_MS,
  DISCLOSURE_MOTION,
  SURFACE_ENTRY_MOTION,
} from "@/lib/motion";
import { SURFACE } from "@/lib/surface";
import type { Tone } from "@/lib/tone";
import { ToneDot } from "@/components/ui/tone-dot";
import {
  applyEvidenceReviewRecommendations,
  evidenceReviewRecommendationSummary,
  reviewQuantitativeCandidateGroup,
} from "@/lib/quantitative-review";
import {
  DocumentSourceContext,
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
import { DisclosureSummary } from "@/components/ui/disclosure-summary";
import { TRIGGER_AT_LINE_START } from "@/components/ui/provenance";
import { TEXT_TOGGLE } from "@/lib/typography";
import { countLabel } from "@/lib/count-label";
import { formatPublishedMonth, formatWindowDate } from "@/lib/published-date";

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
  { key: "units", label: "Extracting document claims" },
  { key: "unit_reconciliation", label: "Reconciling document claims" },
  { key: "targets", label: "Binding document fields" },
  { key: "quantitative_targets", label: "Structuring measurable targets" },
  { key: "target_review", label: "Prefilling numeric target review" },
  { key: "queries", label: "Extracting queries" },
  { key: "search", label: "Searching evidence sources" },
  { key: "announcements", label: "Reading announcements" },
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
 * left to right wants an order. Strongest first so the row opens with what held up; "not
 * searched" and "no target stated" end it because neither is a verdict on evidence: one is
 * the reviewer's choice, the other the document's silence.
 */
const GROUNDING_ORDER = [
  "well_grounded",
  "partial",
  "thin",
  "unsupported",
  "unknown",
  "no_evidence",
  "not_assessed",
  "not_searched",
  "not_stated",
] as const satisfies readonly (EvidenceStrength | "not_stated")[];

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
    // One classification decides both axes, so a failure is named once, by coverage. So is
    // an absence of evidence, which empties both.
    outcome: outcomeIsSeparate(signal) ? OUTCOME_LABEL[signal.outcome] : null,
    tone: OUTCOME_TONE[signal.outcome],
  };
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
          className="min-w-0 truncate group-open/expand:whitespace-normal group-open/expand:overflow-visible group-open/expand:text-clip group-open/expand:break-words"
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
  "not_assessed",
];

function relationCounts(matches: Match[]): RelationCounts {
  return matches.reduce(
    (acc, m) => {
      acc[m.relation] += 1;
      return acc;
    },
    { contradicts: 0, extends: 0, confirms: 0, unrelated: 0, not_assessed: 0 } satisfies RelationCounts,
  );
}

/** Compact source rows with readable titles and trailing metadata; long lists collapse. Used everywhere a
 * finding list appears, so sources look identical across the view. */
function SourceList({ findings }: { findings: Finding[] }) {
  const [showAll, setShowAll] = useState(false);
  if (findings.length === 0) return null;
  const shown = showAll ? findings : findings.slice(0, SOURCE_LIST_LIMIT);
  return (
    <ul className="mt-3 divide-y divide-border/60">
      {shown.map((f, index) => {
        const date = formatPublishedMonth(f.published_at, f.published_precision);
        const sourceLabels = (
          f.source_lanes?.length ? f.source_lanes : [f.source]
        ).map((lane) => sourceDisplayLabel(lane, f.source_labels));
        const sourceLabel = Array.from(new Set(sourceLabels)).join(" + ");
        const meta = [sourceLabel, date].filter(Boolean).join(" · ");
        return (
          // The contract refuses a repeated URL within one list; the index keeps a key
          // unique even so, because a duplicate key silently drops a row.
          <li key={`${index}:${f.url}`} className="grid min-w-0 gap-x-4 gap-y-1 py-2.5 text-xs first:pt-0 sm:grid-cols-[minmax(0,1fr)_minmax(0,11rem)]">
            <a
              href={f.url}
              target="_blank"
              rel="noreferrer"
              title={f.title || f.url}
              className="min-w-0 break-words leading-relaxed text-foreground underline decoration-border underline-offset-2 hover:decoration-current rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/60"
            >
              {f.title || f.url}
            </a>
            <Computed className="break-words text-[11px] leading-relaxed text-muted-foreground sm:text-right">
              {meta}
            </Computed>
          </li>
        );
      })}
      {findings.length > SOURCE_LIST_LIMIT && (
        <li className="pt-2">
          <button
            type="button"
            aria-expanded={showAll}
            onClick={() => setShowAll((v) => !v)}
            className={cn("text-[11px]", TEXT_TOGGLE)}
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
        description={toolAuthority("scout")}
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
  const { result, selectedId, busy, stage, progress, error, startedAt, setResult, setError } = useScoutSession(
    useShallow(({ result, selectedId, busy, stage, progress, error, startedAt, setResult, setError }) =>
      ({ result, selectedId, busy, stage, progress, error, startedAt, setResult, setError })),
  );
  // Read from the run on screen, never held beside it, so switching runs cannot leave
  // one run's checkpoint standing over another.
  const reviewStatus = result ? scoutReviewStatus(result) : null;

  const [showRunPanel, setShowRunPanel] = useState(!result);
  // Scout-only: the retrieval window, declared before the run and carried
  // on the draft so the continuation searches the same cohort.
  const [publishedSince, setPublishedSince] = useState("");

  useEffect(() => {
    if (result) setShowRunPanel(false);
  }, [result]);
  const showSetup = useCallback(() => setShowRunPanel(true), []);

  // Covers arriving with a hash already set, or the back button. The click itself is handled
  // on the link, because clicking a citation whose hash is already current fires no
  // `hashchange` and would otherwise do nothing the second time.
  useEffect(() => {
    const openFromHash = () => revealInsight(window.location.hash.slice(1));
    openFromHash();
    window.addEventListener("hashchange", openFromHash);
    return () => window.removeEventListener("hashchange", openFromHash);
  }, []);

  function handleRun(file: File) {
    void runTool(useScoutSession, (report) => runScout([file], header, { publishedSince }, report));
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

  function handleFieldSearchChange(notSearchedFields: string[]) {
    if (!result || result.phase !== "target_review") return;
    setResult({ ...result, not_searched_fields: notSearchedFields });
  }

  async function handleContinueAnalysis() {
    if (!result || result.phase !== "target_review") return;
    if (pendingQuantitativeReviewCount(result) > 0) {
      setError("Resolve every numeric target review item before continuing.");
      return;
    }
    const blocked = fieldSelectionSummary(result).blocked;
    if (blocked) {
      setError(blocked);
      return;
    }
    const completed = await trackTool(useScoutSession, (report) => continueScout(result, report));
    if (completed) setResult(completed);
  }

  function handleQuantitativeReview(
    targetId: string,
    candidateIds: string[],
    selectedCandidateId: string | null,
  ) {
    if (!result || result.phase !== "evidence_review") return;
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
    setResult({
      ...result,
      conformity: result.conformity.map((score) =>
        score.target_id === targetId ? reviewedScore : score,
      ),
    });
  }

  function handleAcceptEvidenceRecommendations() {
    if (!result || result.phase !== "evidence_review") return;
    const conformity = applyEvidenceReviewRecommendations(result.conformity);
    if (conformity.every((score, index) => score === result.conformity[index]))
      return;
    setResult({ ...result, conformity });
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
  }

  return (
    <div className="flex flex-col gap-6">
      {/* Not while a continuation runs - the only run that starts from a target-review
          draft. That work belongs to the checkpoint on screen, which shows its own progress,
          and mounting setup above it pushed the checkpoint down. */}
      {((busy && result?.phase !== "target_review") || !result || showRunPanel) && (
        <RunPanel
            onCancel={result ? () => setShowRunPanel(false) : undefined}
          configuration={
            <ScoutConfiguration
              publishedSince={publishedSince}
              onPublishedSinceChange={setPublishedSince}
            />
          }
          busy={busy}
          startedAt={startedAt}
          onRun={(files) => handleRun(files.document)}
          steps={SCOUT_STEPS}
          currentStage={stage}
          progress={progress}
          runDisabled={!ready}
          hint={ready ? undefined : "Complete the configuration to run."}
          // A portable result is checked once at the import boundary; import never
          // triggers retrieval.
          onImport={(file) => importTool(useScoutSession, file, unpackScoutResult)}
        />
      )}
      {error && <ErrorMessage>{error}</ErrorMessage>}
      {result && result.phase === "target_review" && (
        <DocumentTargetReviewCheckpoint
          // Keyed by run, so a selection made in one run's review is not carried into another's.
          key={selectedId}
          result={result}
          busy={busy}
          stage={stage}
          progress={progress}
          onTargetDecision={handleTargetDecision}
          onStatementDecision={handleStatementDecision}
          onAcceptRecommendations={handleAcceptTargetRecommendations}
          onFieldSearchChange={handleFieldSearchChange}
          onContinue={handleContinueAnalysis}
          onNewAnalysis={() => setShowRunPanel(true)}
        />
      )}
      {result &&
        result.phase === "evidence_review" && (
          <QuantitativeReviewCheckpoint
            key={selectedId}
            result={result}
            onNewAnalysis={() => setShowRunPanel(true)}
            onReview={handleQuantitativeReview}
            onAcceptRecommendations={handleAcceptEvidenceRecommendations}
            readyToFinalize={reviewStatus === "ready"}
            onFinalize={handleFinalizeReview}
          />
        )}
      {result && result.phase === "final" && (
        <FieldGrid
          key={selectedId}
          result={result}
          onNewAnalysis={showSetup}
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
  onFieldSearchChange,
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
  /** The draft's new `not_searched_fields`: the one record of the reviewer's field choice. */
  onFieldSearchChange: (notSearchedFields: string[]) => void;
  onContinue: () => void;
  onNewAnalysis: () => void;
}) {
  const targets = result.quantitative_ledger.targets;
  const statements = result.quantitative_ledger.reviews.filter(
    (review) =>
      review.classification === "uncertain" ||
      review.classification === "mapping_failed" ||
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

  const activeKey = selectedItem ?? firstPendingKey;
  const target = activeKey?.startsWith("target:")
    ? targets.find((item) => item.id === activeKey.slice("target:".length))
    : undefined;
  const statement = activeKey?.startsWith("statement:")
    ? statements.find(
        (item) => item.unit_id === activeKey.slice("statement:".length),
      )
    : undefined;
  const chatSelection = useMemo<ReviewSelection | null>(() => target
    ? { kind: "target", target_id: target.id }
    : statement ? { kind: "statement", unit_id: statement.unit_id } : null,
  [target?.id, statement?.unit_id]);
  usePublishReviewContext(result, chatSelection);
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
  const fieldSelection = fieldSelectionSummary(result);
  const blockedId = useId();

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
          "overflow-hidden rounded-lg bg-card shadow-raised",
          SURFACE_ENTRY_MOTION,
        )}
      >
        <ReviewCheckpointHeader
          eyebrow="Review checkpoint · Before evidence search"
          since={formatWindowDate(result.published_since)}
          scope={retrievalScopeParts(result.retrieval_scope)}
          fields={
            <FieldSearchSelection
              result={result}
              disabled={busy}
              onChange={onFieldSearchChange}
            />
          }
          notices={<><ContextValidationNotice result={result} /><ReconciliationNotice result={result} /><DocumentExtractionNotice blocks={result.blocks ?? []} hasDocumentsTab={false} /></>}
          title="Review numeric targets"
          description="Confirm that each number and its qualifiers is an intended requirement. Scout searches for evidence on what you confirm."
          help={
            <>
              Check each numeric target against its cited document passages.
              Exclude background numbers, examples, and rejected alternatives;
              acknowledge any unresolved extraction items. These checkpoints
              review numeric targets and their evidence. Nonnumeric claims are
              assessed separately and do not appear here. Excluded items remain
              traceable.
            </>
          }
          completed={completed}
          total={total}
          progressLabel="Numeric target review progress"
          actions={
            <>
              {/* Not while the continuation runs: it writes back to the run on screen. */}
              {!busy && <ScoutRunHistory />}
              <NewAnalysisButton disabled={busy} onClick={onNewAnalysis} />
            </>
          }
        />

        <ReviewOverview
          description="Select an item to check its source. AI recommendations are suggestions until you accept them."
          advance={
            <>
              {/* Said beside the button it disables, so the reason is where the reader looks. */}
              {fieldSelection.blocked && !busy && (
                <span id={blockedId} className="text-[11px] text-muted-foreground">
                  {fieldSelection.blocked}
                </span>
              )}
              <Button
                size="sm"
                disabled={busy || completed !== total || Boolean(fieldSelection.blocked)}
                aria-describedby={fieldSelection.blocked && !busy ? blockedId : undefined}
                onClick={onContinue}
              >
                {busy ? "Searching and assessing evidence…" : "Search for evidence"}
              </Button>
            </>
          }
          counts={
            <>
                <>
                  <ReviewCount
                    tone="success"
                    label={`${confirmedCount} confirmed`}
                  />
                  <ReviewCount
                    tone="neutral"
                    label={`${excludedCount} excluded`}
                  />
                  <ReviewCount tone="warning" label={`${flaggedCount} remaining`} />
                </>
            </>
          }
          actions={
            recommendedTargetCount > 0 ? (
              <Button variant="outline" size="sm" disabled={busy} onClick={onAcceptRecommendations}>
                Accept {countLabel(recommendedTargetCount, "AI recommendation")}
              </Button>
            ) : undefined
          }
        >
          {targets.map((item) => {
            const presentation = targetReviewPresentation(item);
            const selected = activeKey === `target:${item.id}`;
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
                  reviewRecommendationReason(item) ||
                  "No reviewer explanation was returned; manual review is required."
                }
              />
            );
          })}
          {statements.map((item) => {
            const pending = item.review_status === "needs_review";
            const selected = activeKey === `statement:${item.unit_id}`;
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
                    : item.classification === "mapping_failed" ? "Extraction failed" : "Source unclear"
                }
                status={pending ? "Needs review" : "Excluded"}
                tone={pending ? "warning" : "neutral"}
                detail={statementReviewReason(item)}
              />
            );
          })}
        </ReviewOverview>

        {target ? (
          <ReviewDetailColumns
            left={
              // Held in view while the qualifiers beside it are read against it.
              <div className="lg:sticky lg:top-6">
                <div className="flex items-center justify-between gap-3">
                  <SectionLabel>Source passage</SectionLabel>
                  <DocumentSourceTrace
                    blockIds={target.doc_block_ids}
                    spans={target.provenance_spans}
                  />
                </div>
                <Quoted size="prominent">{target.quote}</Quoted>
              </div>
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
                  {(Object.keys(target.semantic_profile) as Array<keyof typeof target.semantic_profile>).filter(dimension =>
                    target.semantic_profile[dimension].state !== "not_specified" || target.comparison_contract[dimension].mode !== "unconstrained",
                  ).map((dimension) => (
                    <div key={dimension} className="min-w-0">
                      <dt className="flex flex-wrap items-center justify-between gap-2">
                        <span className={EYEBROW}>{dimensionLabel(dimension)}</span>
                        <TargetQualifierSource target={target} dimension={dimension} besides={target.doc_block_ids} />
                      </dt>
                      <dd className="mt-1 text-xs leading-relaxed text-foreground">
                        {semanticSlotLabel(target.semantic_profile[dimension])}
                      </dd>
                    </div>
                  ))}
                </dl>
                <TargetComparisonRules target={target} />
                {linkedVariables.length > 0 && <div className="mt-5 border-t border-border/60 pt-4">
                  <SectionLabel>Linked product fields</SectionLabel>
                  <div className="mt-2 space-y-2">
                    {linkedVariables.map(({ link, variable }) => (
                      <div
                        key={`${link.attribute_ref}:${link.relation}`}
                        className="text-[11px] leading-relaxed"
                      >
                        <p>
                          <span className="font-medium text-foreground">
                            {displayAttributeLabel(variable.name)}
                          </span>
                          <span className="text-muted-foreground">
                            {" · "}{link.relation === "context_for" ? "context for this field" : link.relation === "constrains" ? "constrains this field" : "defines this field"}
                          </span>
                        </p>
                        {link.reason && <p className="mt-0.5 text-muted-foreground">{link.reason}</p>}
                      </div>
                    ))}
                  </div>
                </div>}
              </>
            }
          />
        ) : statement ? (
          <div className="p-5 sm:p-6">
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
              <span>{statementReviewReason(statement)}</span>
            </InterfaceNote>
          </div>
        ) : (
          <div className="px-5 py-9 sm:px-6">
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

        {target && <div className="border-t border-border/60 px-5 pb-5 sm:px-6">
          <ReviewRecommendation
            unavailable={target.ai_recommendation === "unavailable"}
            label={aiRecommendationPresentation(target.ai_recommendation).label}
            tone={aiRecommendationPresentation(target.ai_recommendation).tone}
          >{reviewRecommendationReason(target) || "No explanation was returned; review this proposal manually."}</ReviewRecommendation>
        </div>}

        <ReviewDecisionFooter>
          <p className="text-[11px] leading-relaxed text-muted-foreground">
            {busy
              ? `${stage ? (SCOUT_STEPS.find((item) => item.key === stage)?.label ?? stage) : "Continuing analysis"}${progress ? ` · ${progress.completed}/${progress.total}` : ""}`
              : target?.review_status === "approved" ? "Your decision: confirmed. You can change it below."
              : target?.review_status === "rejected" ? "Your decision: excluded. You can change it below."
              : statement?.review_status === "accepted_exclusion" ? "Exclusion acknowledged."
              : "Check the source, then record your decision."}
          </p>
          <ReviewActions>
            {target && (
              <>
                <Button
                  variant="outline"
                  disabled={busy || target.review_status === "rejected"}
                  onClick={() => decideTarget(target.id, "rejected")}
                >
                  Exclude as context
                </Button>
                <Button
                  disabled={busy || target.review_status === "approved"}
                  onClick={() => decideTarget(target.id, "approved")}
                >
                  Confirm target
                </Button>
              </>
            )}
            {statement && (
              <Button
                disabled={busy || statement.review_status === "accepted_exclusion"}
                onClick={() => decideStatement(statement.unit_id)}
              >
                {statement.classification === "partial_target"
                  ? "Acknowledge unresolved remainder"
                  : "Acknowledge exclusion"}
              </Button>
            )}
          </ReviewActions>
        </ReviewDecisionFooter>
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

/** Both checkpoints keep header and footer decisions reachable at narrow widths. */
function ReviewActions({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("flex min-w-0 flex-wrap items-center gap-2", className)}>{children}</div>;
}

function ReviewDecisionFooter({ children }: { children: ReactNode }) {
  return <footer className={cn("flex flex-col gap-3 border-t border-border/60 px-5 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-6", SURFACE.recessed)}>{children}</footer>;
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
  notices,
  since,
  scope = [],
  fields,
}: {
  eyebrow: string;
  title: string;
  description: string;
  help: ReactNode;
  completed: number;
  total: number;
  progressLabel: string;
  actions?: ReactNode;
  notices?: ReactNode;
  /** The run's publication window, declared before retrieval, so the reviewer sees it here. */
  since?: string | null;
  /** What retrieval will search for, resolved before review for the same reason. */
  scope?: ScopePart[];
  /** Which fields the continuation searches, beside the scope it searches them in. */
  fields?: ReactNode;
}) {
  const scopeBlocks = scope.flatMap((part) => part.blockIds);
  return (
    <header className="border-b border-border/60 px-5 py-5 sm:px-6">
      {/* Reserve the actions' width instead of letting the description squeeze them
          into partial rows. Below desktop, place the group under the description. */}
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-start">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5">
            <p className={EYEBROW}>{eyebrow}</p>
            <ReviewHelp>{help}</ReviewHelp>
          </div>
          <h2 className={cn(DISPLAY_HEADING, "mt-1 text-lg font-semibold text-foreground")}>
            {title}
          </h2>
          <SectionDescription>{description}</SectionDescription>
          {since && (
            <p className="mt-2 flex items-center gap-1.5 text-xs text-muted-foreground">
              <CalendarRange aria-hidden="true" className="h-3.5 w-3.5 shrink-0" />
              Evidence published since {since}; sources that state no date are included.
            </p>
          )}
          {scope.length > 0 && (
            // A div, not a p: the source trigger opens a panel, which a paragraph cannot hold.
            <div className="mt-2 flex flex-wrap items-center gap-x-1.5 gap-y-1 text-xs text-muted-foreground">
              <Search aria-hidden="true" className="h-3.5 w-3.5 shrink-0" />
              <span>Search scope: {scope.map((part) => part.text).join(" · ")}</span>
              {scopeBlocks.length > 0 && <DocumentSourceTrace blockIds={scopeBlocks} />}
            </div>
          )}
          {fields}
        </div>
        {actions && (
          <ReviewActions className="flex-col items-stretch sm:flex-row sm:flex-nowrap sm:justify-end">
            {actions}
          </ReviewActions>
        )}
      </div>
      <div className="mt-4 flex items-center gap-3">
        <div
          className={cn("h-1.5 min-w-0 flex-1 overflow-hidden rounded-full", SURFACE.fill)}
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
      {notices && <ResultNotices className="mt-4">{notices}</ResultNotices>}
    </header>
  );
}

/**
 * Which fields the continuation searches: every searchable field, until the reviewer says
 * otherwise.
 *
 * Closed on arrival, behind its count, because the default needs nothing from anyone: one
 * quiet line under the search scope, which is what it qualifies. Opened, it lists the fields
 * that state a target as the same chips Searcher's sources use. The draft's
 * `not_searched_fields` is the only record of the choice; nothing here holds a copy.
 */
function FieldSearchSelection({
  result,
  disabled,
  onChange,
}: {
  result: ScoutResponse;
  disabled: boolean;
  onChange: (notSearchedFields: string[]) => void;
}) {
  const fields = searchableFields(result);
  if (fields.length === 0) return null;
  const summary = fieldSelectionSummary(result);
  const excluded = new Set(result.not_searched_fields ?? []);
  return (
    <details className="mt-2 text-xs text-muted-foreground">
      <DisclosureSummary className="w-fit rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/60">
        Fields to search{" "}
        <span className="text-[11px] tabular-nums">
          {summary.searched} of {summary.total}
        </span>
      </DisclosureSummary>
      <fieldset className={cn("mt-2 min-w-0 pl-5", DISCLOSURE_MOTION)}>
        <legend className="sr-only">Fields to search</legend>
        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
          <p role="status">
            {summary.sentence} A field left out stays in the result as not searched.
          </p>
          {/* Two quick actions, because the common edits are "only these few" and "back to
              every field", and each would otherwise take one click per field. */}
          <div className="flex items-center gap-1">
            <Button
              variant="quiet"
              size="toolbar"
              disabled={disabled || summary.searched === summary.total}
              onClick={() => onChange(withEveryFieldSearched(result, true))}
            >
              Select all
            </Button>
            <Button
              variant="quiet"
              size="toolbar"
              disabled={disabled || summary.searched === 0}
              onClick={() => onChange(withEveryFieldSearched(result, false))}
            >
              Clear all
            </Button>
          </div>
        </div>
        <div className="mt-2 flex flex-wrap gap-2">
          {fields.map((variable) => {
            const searched = !excluded.has(variable.name);
            return (
              <ConfigChip
                key={variable.name}
                selected={searched}
                disabled={disabled}
                onClick={() => onChange(withFieldSearched(result, variable.name, !searched))}
              >
                {displayAttributeLabel(variable.name)}
              </ConfigChip>
            );
          })}
        </div>
      </fieldset>
    </details>
  );
}

function ReviewOverview({
  description,
  counts,
  actions,
  advance,
  children,
}: {
  description: string;
  counts: ReactNode;
  actions?: ReactNode;
  advance?: ReactNode;
  children: ReactNode;
}) {
  const listRef = useRef<HTMLDivElement>(null);
  // Keep auto-advance visible inside the list without moving the whole page.
  useEffect(() => {
    const list = listRef.current;
    const active = list?.querySelector<HTMLElement>('[aria-current="true"]');
    if (!list || !active) return;
    const bounds = list.getBoundingClientRect();
    const row = active.getBoundingClientRect();
    if (row.top < bounds.top) list.scrollTop += row.top - bounds.top;
    else if (row.bottom > bounds.bottom) list.scrollTop += row.bottom - bounds.bottom;
  });
  return (
    <div className={cn("border-b border-border/60 px-5 py-5 sm:px-6", SURFACE.recessed)}>
      <div className="space-y-4">
        <div>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h3 className="text-sm font-semibold text-foreground">
              Review items
            </h3>
            <div className="flex flex-wrap gap-x-4 gap-y-2 text-[11px] tabular-nums text-muted-foreground" role="status">{counts}</div>
          </div>
          <SectionDescription>{description}</SectionDescription>
        </div>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <ReviewActions>{actions}</ReviewActions>
          <ReviewActions>{advance}</ReviewActions>
        </div>
      </div>
      <div ref={listRef} className="mt-4 max-h-72 overflow-y-auto rounded-lg border border-border/60 bg-card">
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
  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        "grid w-full gap-2 px-4 py-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring/60 motion-reduce:transition-none sm:grid-cols-[minmax(0,1fr)_minmax(9rem,auto)] sm:items-center",
        SURFACE.hover,
        selected ? SURFACE.selected : "bg-card",
      )}
      aria-current={selected ? "true" : undefined}
    >
      <span className="min-w-0">
        <span className="block break-words text-xs font-medium text-foreground">
          {title}
        </span>
        <span className="mt-0.5 block break-words text-[11px] text-muted-foreground">
          {subtitle}
        </span>
        <span className="mt-1 block truncate text-[11px] text-muted-foreground">{detail}</span>
      </span>
      <VerdictPill label={status} tone={tone === "positive" ? "success" : tone} className="w-fit sm:justify-self-end" />
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
      <div className="min-w-0 border-b border-border/60 p-5 sm:p-6 lg:border-b-0 lg:border-r">
        {left}
      </div>
      <div className="min-w-0 p-5 sm:p-6">{right}</div>
    </div>
  );
}

function ReviewRecommendation({
  label,
  tone,
  children,
  unavailable = false,
}: {
  label: string;
  tone: ReviewTone;
  children: ReactNode;
  unavailable?: boolean;
}) {
  return (
    <div className={cn("mt-4 rounded-lg border border-border/60 p-3", SURFACE.recessed)}>
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-sm font-semibold text-foreground">{unavailable ? "Independent AI review unavailable" : "Independent AI recommendation"}</h3>
        <VerdictPill label={label} tone={tone === "positive" ? "success" : tone} />
      </div>
      {unavailable ? <InterfaceNote>{children} You can still review the source and record your own decision.</InterfaceNote> : <Reading>{children}</Reading>}
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
  if (target.ai_recommendation === "unavailable")
    return { label: "AI review unavailable", tone: "warning" };
  return { label: "Needs review", tone: "warning" };
}

function aiRecommendationPresentation(
  recommendation: QuantitativeTarget["ai_recommendation"],
): { label: string; tone: ReviewTone } {
  if (recommendation === "confirm")
    return { label: "Confirm", tone: "positive" };
  if (recommendation === "exclude")
    return { label: "Exclude", tone: "neutral" };
  if (recommendation === "unavailable")
    return { label: "Review unavailable", tone: "warning" };
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
  if (pending.some((item) => item.ai_recommendation === "unavailable")) {
    return { label: "AI review unavailable", tone: "warning" };
  }
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

/** Viewing an estimate is separate from admitting it. Recorded decisions win over AI hints. */
function defaultReviewEstimateId(measurements: Measurement[]): string | null {
  return measurements.find(item => item.admission_status === "approved")?.candidate_id
    ?? measurements.find(item => item.admission_status === "needs_review" && item.ai_recommendation === "admit")?.candidate_id
    ?? (measurements.every(item => item.admission_status !== "needs_review")
      ? measurements[0]?.candidate_id ?? null : null);
}

function ReviewEstimateChoices({ measurements, selectedId, onSelect, pending }: {
  measurements: Measurement[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  pending: boolean;
}) {
  const name = useId();
  return (
    <fieldset className="min-w-0">
      <legend className={EYEBROW}>{pending ? "Choose one estimate" : "Inspect estimates"}</legend>
      <SectionDescription>
        {pending
          ? "These estimates are grouped to avoid counting overlapping evidence twice. Select one to inspect, then admit it or reject all."
          : "Select an estimate to inspect it. Use the decision buttons below to change which estimate is admitted."}
      </SectionDescription>
      <div className="mt-3 space-y-2">
        {measurements.map(item => {
          const presentation = evidenceReviewPresentation([item]);
          return (
            <label key={item.candidate_id} className={cn(
              "flex cursor-pointer items-start gap-3 rounded-lg border p-3 transition-colors focus-within:ring-2 focus-within:ring-ring motion-reduce:transition-none",
              selectedId === item.candidate_id ? cn("border-foreground/45", SURFACE.selected) : cn("border-border/60", SURFACE.hover),
            )}>
              <input type="radio" name={name} value={item.candidate_id}
                checked={selectedId === item.candidate_id}
                onChange={() => onSelect(item.candidate_id)}
                className="mt-1 h-4 w-4 shrink-0 accent-foreground" />
              <span className="min-w-0 flex-1">
                <span className="flex flex-wrap items-center justify-between gap-2">
                  <span className="text-sm font-semibold text-foreground">{formatNumericExpression(item.expression)}</span>
                  <VerdictPill label={presentation.label} tone={presentation.tone === "positive" ? "success" : presentation.tone} />
                </span>
                <span className="mt-1 block text-[11px] text-muted-foreground">{evidenceUnitLabel(item)}</span>
                <span className="mt-1 line-clamp-2 break-words text-xs leading-relaxed text-foreground">{item.source_quote}</span>
              </span>
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}

function QuantitativeReviewCheckpoint({
  result,
  onNewAnalysis,
  onReview,
  onAcceptRecommendations,
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
  const estimateOrder = useRef<string[]>([]);
  for (const { measurement } of allCandidates) {
    if (!estimateOrder.current.includes(measurement.candidate_id)) estimateOrder.current.push(measurement.candidate_id);
  }
  allCandidates.sort((a, b) => estimateOrder.current.indexOf(a.measurement.candidate_id) - estimateOrder.current.indexOf(b.measurement.candidate_id));
  const grouped = new Map<string, typeof allCandidates>();
  for (const item of allCandidates) {
    const unitId =
      item.measurement.evidence_unit_id || item.measurement.source_record_id;
    const key = `${item.score.target_id}::${unitId}`;
    grouped.set(key, [...(grouped.get(key) ?? []), item]);
  }
  // Inclusion moves estimates between arrays, but must not move the reader's rows.
  const order = useRef<string[]>([]);
  for (const key of grouped.keys()) if (!order.current.includes(key)) order.current.push(key);
  const groups = Array.from(grouped.entries()).sort(([a], [b]) => order.current.indexOf(a) - order.current.indexOf(b));
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
  const defaultCandidateId = defaultReviewEstimateId(current?.[1].map(item => item.measurement) ?? []);
  const [estimateSelection, setEstimateSelection] = useState<{ group: string; candidate: string } | null>(null);
  const selectedCandidateId = estimateSelection?.group === current?.[0]
    && current?.[1].some(item => item.measurement.candidate_id === estimateSelection.candidate)
    ? estimateSelection.candidate : defaultCandidateId;
  const chatSelection = useMemo<ReviewSelection | null>(() => current ? {
    kind: "evidence", target_id: current[1][0].score.target_id,
    candidate_ids: current[1].map(item => item.measurement.candidate_id),
    selected_candidate_id: selectedCandidateId,
  } : null, [result, current?.[0], selectedCandidateId]);
  usePublishReviewContext(result, chatSelection);
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
      ))
    : reviewItems[0];
  const measurement = activeItem?.measurement;
  const target: QuantitativeTarget | undefined =
    result.quantitative_ledger.targets.find(
      (item) => item.id === score.target_id,
    );
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
    onReview(
      score.target_id,
      groupItems.map(({ measurement: item }) => item.candidate_id),
      selectedId,
    );
    const nextKey = pendingGroups.find(([key]) => key !== currentGroupKey)?.[0];
    setEstimateSelection(null);
    if (pendingItems.length > 0 && nextKey) setSelectedGroupKey(nextKey);
  }

  return (
    <DocumentSourceProvider blocks={result.blocks ?? []}>
      <section
        className={cn(
          "overflow-hidden rounded-lg bg-card shadow-raised",
          SURFACE_ENTRY_MOTION,
        )}
      >
        <ReviewCheckpointHeader
          eyebrow="Review checkpoint · Before final result"
          since={formatWindowDate(result.published_since)}
          scope={retrievalScopeParts(result.retrieval_scope)}
          notices={<><ContextValidationNotice result={result} /><ReconciliationNotice result={result} /><DocumentExtractionNotice blocks={result.blocks ?? []} hasDocumentsTab={false} /></>}
          title="Review quantitative evidence"
          description="Decide which measurements are comparable to the document’s targets and can enter the statistics."
          help={
            <>
              Check each evidence measurement against the numeric target’s required
              comparison criteria and qualifiers. Admit comparable measurements
              whether or not their values meet the target. These decisions control
              comparator statistics, not the assessment of nonnumeric claims.
              Rejected evidence remains traceable but cannot enter statistics.
            </>
          }
          completed={completed}
          total={total}
          progressLabel="Quantitative evidence review progress"
          actions={
            <>
              <ScoutRunHistory />
              <NewAnalysisButton onClick={onNewAnalysis} />
            </>
          }
        />

        <ReviewOverview
          description="Select an item to compare its source with the target. AI recommendations are suggestions until you accept them."
          advance={<Button size="sm" disabled={!readyToFinalize} onClick={onFinalize}>Finalize result</Button>}
          counts={
            <>
                <>
                  <ReviewCount
                    tone="success"
                    label={`${admittedGroupCount} admitted`}
                  />
                  <ReviewCount
                    tone="neutral"
                    label={`${rejectedGroupCount} rejected`}
                  />
                  <ReviewCount tone="warning" label={`${pendingGroups.length} remaining`} />
                </>
            </>
          }
          actions={
            actionableRecommendations > 0 ? (
              <Button variant="outline" size="sm" onClick={onAcceptRecommendations}>
                Accept {countLabel(actionableRecommendations, "AI recommendation")}
              </Button>
            ) : undefined
          }
        >
          {groups.map(([key, items]) => {
            const representative =
              items.find(
                ({ measurement: item }) =>
                  item.admission_status === "needs_review",
              ) ?? items.find(({ measurement: item }) => item.admission_status === "approved") ?? items[0];
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
                onSelect={() => { setSelectedGroupKey(key); setEstimateSelection(null); }}
                title={formatAttributeRefs(
                  representative.score.attribute_refs,
                  "Document claim",
                )}
                subtitle={`${items.length > 1 ? `${items.length} estimates` : formatNumericExpression(representative.measurement.expression)} compared with a target of ${rowTarget ? formatNumericExpression(rowTarget.expression) : representative.score.target_label}`}
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
              {multiple && (
                <ReviewEstimateChoices
                  measurements={reviewItems.map(item => item.measurement)}
                  selectedId={selectedCandidateId}
                  onSelect={candidate => setEstimateSelection({ group: currentGroupKey, candidate })}
                  pending={pendingItems.length > 0}
                />
              )}
              {measurement && (
                <div className={multiple ? "mt-5" : undefined}>
                  <SectionLabel>{multiple ? "Selected estimate" : "Cited evidence"}</SectionLabel>
                  <p className="mt-3 text-base font-semibold text-foreground">
                    {formatNumericExpression(measurement.expression)}
                  </p>
                  <Quoted size="prominent" collapsible>{measurement.source_quote}</Quoted>
                  <a
                    href={measurement.url}
                    target="_blank"
                    rel="noreferrer"
                    className="mt-3 block break-words text-xs font-medium text-muted-foreground underline underline-offset-2 hover:text-foreground rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/60"
                  >
                    {(activeItem && sourceFindingFor(activeItem)?.title) ||
                      measurement.source_record_id ||
                      "Open cited source"}
                  </a>
                </div>
              )}
            </>
          }
        />

        <div className="border-t border-border/60 px-5 py-5 sm:px-6">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <SectionLabel>Comparison check</SectionLabel>
          </div>
          {measurement ? (
            <ScoutComparison target={target} measurement={measurement} />
          ) : (
            <p className="mt-3 rounded-lg border border-dashed border-border px-4 py-5 text-xs text-muted-foreground">
              Select an estimate above to inspect how it maps to the document
              target.
            </p>
          )}
          {measurement && (
            <ReviewRecommendation
              unavailable={measurement.ai_recommendation === "unavailable"}
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
              {reviewRecommendationReason(measurement) ||
                "No complete independent recommendation was returned."}
            </ReviewRecommendation>
          )}
        </div>

        <ReviewDecisionFooter>
          <p className="text-[11px] leading-relaxed text-muted-foreground">
            {pendingItems.length > 0 ? (multiple ? "Choose one estimate to admit, or reject all estimates." : "Judge comparability, not whether the value meets the target.") : "Decision recorded. You can change it below."}
          </p>
          <ReviewActions>
              <>
                <Button variant="outline" disabled={groupItems.every(item => item.measurement.admission_status === "rejected")} onClick={() => decideCurrent(null)}>
                  {multiple ? "Reject all estimates" : "Reject measurement"}
                </Button>
                <Button
                  disabled={(multiple && selectedCandidateId == null) || measurement?.admission_status === "approved"}
                  onClick={() =>
                    decideCurrent(
                      multiple
                        ? selectedCandidateId
                        : groupItems[0].measurement.candidate_id,
                    )
                  }
                >
                  {multiple ? "Admit selected estimate" : "Admit measurement"}
                </Button>
              </>
          </ReviewActions>
        </ReviewDecisionFooter>
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
          className="rounded-full text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/60 motion-reduce:transition-none"
        >
          <CircleHelp className="h-3.5 w-3.5" />
        </button>
      </PopoverTrigger>
      <HelpPopoverContent>
        {children}
      </HelpPopoverContent>
    </Popover>
  );
}

function ContextValidationNotice({ result }: { result: ScoutResponse }) {
  const validation = result.context_validation;
  if (!validation || validation.status === "match") return null;

  // `not_assessed` is not the model's `uncertain`: the check obtained no answer at all, so
  // its reason is the pipeline's diagnostic rather than a reading, and is not set in a
  // model's voice.
  const unassessed = validation.status === "not_assessed";
  const message = unassessed
    ? `Scout could not check whether the document concerns ${validation.configured_indication}; the run continued without that check.`
    : validation.status === "mismatch"
      ? `The document appears to concern ${validation.document_indication || "a different disease or health need"}, not ${validation.configured_indication}.`
      : `Scout could not confidently verify that the document concerns ${validation.configured_indication}.`;

  return (
    <WarningNotice label="Review document context">
      <div className="min-w-0">
        <p className="font-medium">Review document context</p>
        {/* The tool's own statement of what it found, then the model's reason for it. They
            were one paragraph, which put a sentence the interface composed and a sentence a
            model wrote in the same voice. */}
        <p className="mt-0.5 leading-relaxed text-muted-foreground">
          {message}
        </p>
        {!unassessed && (
          <Reading size="prominent" className="mt-1">
            {validation.reason}
          </Reading>
        )}
        <p className="mt-1.5 leading-relaxed text-muted-foreground">
          Check the selected disease or health need against the original document
          before relying on the evidence. If the selection or document is wrong,
          start a new analysis with the correct inputs.
        </p>
      </div>
    </WarningNotice>
  );
}

/**
 * Checks a stage could not complete, summed across the result.
 *
 * Each one is kept and marked "not assessed" where it appears, which is right for a reader
 * who arrives at that row and invisible to one reading the run as a whole: a field list in
 * which some relations were never obtained looks exactly like one in which none were
 * found. So the sum is a warning, beside the other facts that change what the run says.
 */
function UnassessedChecksNotice({ result }: { result: ScoutResponse }) {
  const checks = unassessedChecks(result);
  if (checks.total === 0) return null;
  return (
    <WarningNotice label="Checks not completed">
      <div className="min-w-0">
        <p className="font-medium">
          {checks.total === 1
            ? "1 check could not be completed"
            : `${checks.total} checks could not be completed`}
        </p>
        <p className="mt-0.5 leading-relaxed text-muted-foreground">
          {checks.parts.join(", ")}. Each is marked Not assessed where it appears, and
          nothing was concluded about it. Run the analysis again to retry them.
        </p>
      </div>
    </WarningNotice>
  );
}

/**
 * Sets whose duplicate check did not complete, so a duplicate in them may count twice.
 *
 * A caveat rather than a warning: the run went on with the set unmerged, every item in it
 * is real and traceable, and only how far its counts can be taken changes.
 */
function ReconciliationNotice({ result }: { result: Pick<ScoutResponse, "reconciliations"> }) {
  const sets = unreconciledSets(result.reconciliations);
  if (sets.length === 0) return null;
  return (
    <CaveatNotice label="Duplicates not merged">
      Scout could not check {new Intl.ListFormat("en", { type: "conjunction" }).format(sets)} for
      duplicates, so the same item there may be counted more than once.
    </CaveatNotice>
  );
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

/**
 * The run picker, wherever a Scout run is shown: a review checkpoint as well as a result.
 *
 * Only the final result drew it, so selecting a run paused at a checkpoint left no way
 * back to the others.
 */
function ScoutRunHistory() {
  const { results, selectedId, selectResult, removeResult } = useScoutSession(
    useShallow(({ results, selectedId, selectResult, removeResult }) =>
      ({ results, selectedId, selectResult, removeResult })),
  );
  return (
    <RunHistory
      runs={results}
      selectedId={selectedId}
      onSelect={selectResult}
      onRemove={removeResult}
      label={(value) => runLabel(value, "scout")}
    />
  );
}

/** Every field joined to its matches, assessment, comparisons and precedent, in reading order. */
function fieldGridRows(result: ScoutResponse) {
  const matchesByVariable = new Map<string, Match[]>();
  for (const match of result.matches ?? []) {
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

  const rows = (result.variables ?? [])
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
        // Fields left out at review last: they hold nothing to read, only that choice.
        Number(isNotSearched(a.assessment)) - Number(isNotSearched(b.assessment)) ||
        RELATION_ORDER[a.leadingRelation] - RELATION_ORDER[b.leadingRelation] ||
        displayAttributeLabel(a.variable.name).localeCompare(
          displayAttributeLabel(b.variable.name),
        ),
    );

  // The measurable target behind each conformity. `Conformity` carries a pre-joined
  // `target_label` - six semantic slots flattened into one dot-separated run-on - while
  // `QuantitativeTarget.semantic_profile` holds those slots named and separate. The
  // review checkpoint already renders them that way; the result view was reading the
  // flattened copy.
  const targetsById = new Map(
    result.quantitative_ledger.targets.map((target) => [target.id, target]),
  );
  return { rows, headline: runHeadline(rows), targetsById };
}

/** Whether the reviewer left this field out of evidence search at target review. */
function isNotSearched(assessment: EvidenceAssessment | null): boolean {
  return assessment?.strength === "not_searched";
}

/** Memoized so a run's progress ticks, which re-render the page, leave a held result alone. */
const FieldGrid = memo(function FieldGrid({
  result,
  onNewAnalysis,
}: {
  result: ScoutResponse;
  onNewAnalysis: () => void;
}) {
  const { results, selectedId } = useScoutSession(
    useShallow(({ results, selectedId }) => ({ results, selectedId })),
  );
  const held = results.find((entry) => entry.id === selectedId);
  const priorityFindings = useMemo(() => scoutPriorityFindings(result), [result]);
  const priorityReading = usePriorityReading(selectedId, {
    authority: toolAuthority("scout"),
    focus: SCOUT_PRIORITY_FOCUS,
    findings: priorityFindings,
    org: result.org ?? "",
    interventionClass: result.intervention_class ?? "",
    indication: result.indication ?? "",
  });
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
  // Joined, sorted and indexed once per result rather than on every keystroke: the
  // search below only filters what this built.
  const { rows, headline, targetsById } = useMemo(() => fieldGridRows(result), [result]);
  // Deferred, so typing stays responsive while the field rows re-render behind it.
  const normalizedQuery = normalizeQuery(useDeferredValue(query));
  const visibleRows = useMemo(
    () => rows.filter((row) =>
      matchesQuery(normalizedQuery, displayAttributeLabel(row.variable.name), row.variable.description)
      && (relationFilter === "all" || row.matches.some((match) => match.relation === relationFilter))),
    [rows, normalizedQuery, relationFilter],
  );
  if (variables.length === 0) {
    return (
      <EmptyState message="No variables were returned for this intervention." />
    );
  }

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
          notices={<>
            {/* Most consequential first. Fields that could not be bound stopped the run
                short and a doubtful document context changes what it is about, so both are
                warnings; numbers held out of calibration and extracted PDF text only limit
                how far its words go, so they are caveats and follow. */}
            {unresolvedFieldCount > 0 && (
              <WarningNotice label="Document interpretation limitations">
                <div>
                  <p>
                    Document interpretation stopped before retrieval because{" "}
                    {unresolvedFieldCount}{" "}
                    {unresolvedFieldCount === 1 ? "field" : "fields"} could
                    not be bound safely.
                  </p>
                  <p className="mt-1.5">
                    Try running the analysis again. If the issue persists,
                    report it through Feedback with the downloaded JSON.
                  </p>
                  <details className="mt-1.5">
                    <DisclosureSummary className="w-fit rounded-sm font-medium text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/60">
                      Review unresolved fields
                    </DisclosureSummary>
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
              </WarningNotice>
            )}
            <ContextValidationNotice result={result} />
            <UnassessedChecksNotice result={result} />
            {result.quantitative_ledger.status === "uncertain" && (
              <CaveatNotice label="Unresolved numeric statements">
                Some numeric statements remained unresolved after one retry. They were
                retained for audit and excluded from quantitative calibration; the verified
                document claims still proceeded through evidence retrieval.
              </CaveatNotice>
            )}
            <ReconciliationNotice result={result} />
            <DocumentExtractionNotice blocks={result.blocks ?? []} />
          </>}
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
          // "Every field", not "the fields examined": the distribution also holds the fields
          // that stated no target and those left out at review, and neither was examined.
          metricsNote="Grounding sums to every field, including any not stated or not searched; precedent and quantitative comparisons are counted separately. Insights are counted within fields, sources across the whole run."
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
            // Every point rests on fields, so it shows where the fields are.
            tab: "fields",
            panel: <PriorityPanel findings={priorityFindings} reading={priorityReading} />,
          }}
          footer={
            <SourceAttributions
              findings={resultFindings(result)}
              className="border-t border-border/60 px-5 py-3 sm:px-6"
            />
          }
          actions={
            <>
              <ScoutRunHistory />
              <FinalResultActions
                onNewAnalysis={onNewAnalysis}
                download={held && {
                  filename: runFilename("scout"),
                  data: () => packScoutResult(result, held),
                }}
                // A review checkpoint is still being decided, so only a final result exports.
                word={result.phase === "final" ? {
                  tool: "scout",
                  result,
                  onError: (message) => useScoutSession.getState().setError(message),
                } : undefined}
              />
            </>
          }
        >
          <TabsContent value="fields" className="m-0">
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
              <EmptyState className="m-5 sm:m-6" message="No fields match this view" />
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
});


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
  { value: "not_assessed", label: "Not assessed" },
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
}: {
  query: string;
  onQueryChange: (value: string) => void;
  relationship: ProjectionRelationshipFilter;
  onRelationshipChange: (value: ProjectionRelationshipFilter) => void;
  searchLabel: string;
  placeholder: string;
  visibleCount: number;
  totalCount: number;
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
  grouped = false,
}: {
  relationship: TargetRelationship;
  sourceRole: SourceRole;
  grouped?: boolean;
}) {
  if (grouped && sourceRole === "unknown") return null;
  return (
    <div className="mt-2 flex flex-wrap items-center gap-2">
      {!grouped && <Badge variant="outline">{relationshipLabel(relationship)}</Badge>}
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
 * What the announcements could not tell the landscape, said only when it changes how to read it.
 *
 * A reading that failed may hide a program, which is a limit on the landscape, so it is a
 * caveat. With no program at all, the count of announcements read is what separates a weak
 * reading from a quiet week. Beside a landscape of programs the counts said nothing a reader
 * acts on, and stood as a boxed note under every run.
 */
function AnnouncementReading({ stats, programs }: { stats?: FunnelStats; programs: number }) {
  const read = stats?.announcements_read ?? 0;
  const failed = stats?.announcements_failed ?? 0;
  if (failed > 0) {
    return (
      <div className="mx-5 my-4 sm:mx-6">
        <CaveatNotice label="Announcements not read">
          <Computed>{failed.toLocaleString()}</Computed> announcement{failed === 1 ? "" : "s"} could not be
          read, so a program {failed === 1 ? "it names" : "they name"} may be missing here.
        </CaveatNotice>
      </div>
    );
  }
  if (read === 0 || programs > 0) return null;
  return (
    <InterfaceNote className="mx-5 mb-4 sm:mx-6">
      <Computed>{read.toLocaleString()}</Computed> announcement{read === 1 ? " was" : "s were"} read,
      and none named a development program.
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
  const normalizedQuery = normalizeQuery(query);
  const visible = filterProjectionsByRelationship(programs, relationship).filter(
    (program) => matchesQuery(
      normalizedQuery,
      program.name,
      ...program.sponsors,
      ...program.phases,
      ...program.statuses,
    ),
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
          <summary className="flex cursor-pointer select-none items-center gap-2 px-5 py-2.5 outline-none transition-colors hover:bg-foreground/[0.045] focus-visible:bg-foreground/[0.045] focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring/60 sm:px-6 [&::-webkit-details-marker]:hidden motion-reduce:transition-none">
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
                    <h3 className="break-words text-sm font-semibold leading-relaxed text-foreground">
                      {program.name}
                    </h3>
                    <ProjectionRoleLabels
                      grouped
                      relationship={program.target_relationship}
                      sourceRole={program.source_role}
                    />
                    <div className="mt-3 grid gap-x-6 gap-y-3 sm:grid-cols-2 lg:grid-cols-4">
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
                      Records <span className="text-[11px] tabular-nums">{program.supporting_findings.length}</span>
                    </span>
                    <ChevronDown aria-hidden="true" className="h-4 w-4 text-muted-foreground transition-transform group-open/expand:rotate-180 motion-reduce:transition-none" />
                  </div>
                </summary>
                <div
                  className={cn(
                    "space-y-4 border-t border-border/60 px-5 py-5 sm:px-6",
                    SURFACE.open.body,
                    DISCLOSURE_MOTION,
                  )}
                >
                  <ContextualProjectionNote
                    relationship={program.target_relationship}
                    kind="development record"
                  />
                  {verdictReason(program.target_relationship, program.target_relationship_reason) && (
                    <Reading size="prominent" className="mt-0 max-w-[85ch]">
                      {program.target_relationship_reason}
                    </Reading>
                  )}
                  {/* One line, as on a safety observation: a third disclosure level under the
                      group and the record held a list most readers take in at a glance. */}
                  {program.attribute_refs.length > 0 && (
                    <p className="text-[11px] text-muted-foreground">
                      Retrieved for {program.attribute_refs.map(displayAttributeLabel).join(" · ")}
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
        <EmptyState className="m-5 sm:m-6" message="No development records match this view" />
      )}
      <AnnouncementReading stats={stats} programs={programs.length} />
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
                    {verdictReason(observation.target_relationship, observation.target_relationship_reason) && (
                      <Reading className="mt-3 max-w-4xl">
                        {observation.target_relationship_reason}
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
        <EmptyState className="m-5 sm:m-6" message="No safety observations match this view" />
      )}
    </section>
  );
}

/**
 * How much of the document was testable, in one line.
 *
 * Deliberately *not* the answer. The fields below own that, and the priority card reads
 * them - so naming the contradicting fields here said the same thing twice, directly above
 * rows that say it with the evidence, the reason and a source link.
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
        // Counted, not named: the field name is right below, and one of them renders as
        // "I E Ddi", which helps nobody.
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
  // Left out at review: the document's target is shown, and nothing a search would produce.
  const notSearched = isNotSearched(assessment);
  // Built once per field: every signal cites into this instead of re-rendering insights.
  const registry = insightRegistry(matches);
  // `document_spans` reconstructs `document_target` exactly, already split one entry per
  // source table row and each carrying its own blocks. `assessment.doc_target` is only
  // ever a copy of `Variable.document_target` (verified in `evidence_assessor.py`), so
  // rendering the spans shows the same text once, as rows.
  const { blocksById } = useContext(DocumentSourceContext);
  const targetRows = documentTargetRows(documentSpans, blocksById);
  return (
    <details className="group/expand border-b border-border/60 last:border-b-0">
      <summary className={cn(EXPANDABLE_ROW, "justify-between")}>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2">
            <h3 className={ROW_TITLE}>
              {displayAttributeLabel(name)}
            </h3>
          </div>
          {/* The field's own definition, which is project copy rather than anyone's reading
              of this document, so it takes the same shape as the sentence under a section
              heading. Preview two lines in the index; opening the row reveals it all. */}
          {/* Only once the row is open. In the index it was two lines of definition under
              every field - written for the model that reads the document, so "Claims
              about…" and "Includes Minimum and Preferred…" - between the reader and the
              signals they were scanning for. */}
          <SectionDescription className="hidden max-w-[85ch] group-open/expand:block">
            {description}
          </SectionDescription>
          {targetNotStated ? (
            <p className="mt-2 text-xs text-muted-foreground">
              Not stated in document · no evidence analysis was run
            </p>
          ) : notSearched ? (
            <p className="mt-2 text-xs text-muted-foreground">
              Not searched · excluded at review
            </p>
          ) : (
            <ScoutFieldSummary
              relations={counts}
              strength={assessment?.strength ?? null}
              precedent={precedent ?? null}
              targetCount={conformities.length}
              comparatorCount={comparatorCount}
              insightCount={matches.length}
            />
          )}
        </div>
        <ChevronDown className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground transition-transform group-open/expand:rotate-180 motion-reduce:transition-none" />
      </summary>

      {/* The lighter half of the open row's tint, so the row reads as one block from its
          summary to its last line. Tinting the summary alone marked where an open row began
          and never where it ended. */}
      <div
        className={cn(
          "space-y-6 border-t border-border/60 px-5 py-6 sm:px-6",
          SURFACE.open.body,
          DISCLOSURE_MOTION,
        )}
      >
        {/* The document's target and how retrieval was aimed at it are one block: the
            evidence line is that target's footer, so it sits close under it rather than a
            full section gap away, where it read as a section with no heading. The quote row
            already ends in padding and the Searches trigger carries its own height, so a
            small gap here is what reads as attached. */}
        <div className="space-y-1">
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
          {notSearched ? (
            <InterfaceNote className="mt-1">{verdictNote("not_searched")}</InterfaceNote>
          ) : (
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
          )}
        </div>
        {/* One section for the numeric targets whether there are any or not. The slot used
            to change shape with its content - a caps heading with rows when targets
            existed, a bold sentence when they did not - so one fact appeared at two
            altitudes. The dispositions nest here rather than sitting beside Grounding and
            Precedent: they explain this section, they are not a fourth assessment. */}
        {!targetNotStated && !notSearched &&
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
                          <Quoted collapsible size="prominent">{item.quote}</Quoted>
                          {/* A recorded failure is explained in the tool's voice; its
                              reason is the pipeline's, not a model's reading. */}
                          {item.failure_code ? (
                            <InterfaceNote className="mt-1">
                              {statementReviewReason({ ...item, classification: item.disposition })}
                            </InterfaceNote>
                          ) : item.reason && <Reading>{item.reason}</Reading>}
                          <div className={TRIGGER_AT_LINE_START}>
                            <DocumentSourceTrace blockIds={item.block_ids} />
                          </div>
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
        {!targetNotStated && !notSearched &&
          (assessment || precedent || matches.length > 0) && (
            <div className="border-t border-border/60 pt-4">
              {assessment && evidenceTone && (
                <SignalVerdict
                  label="Grounding"
                  chips={[
                    {
                      tone: evidenceTone,
                      text: GROUNDING_LABEL[assessment.strength],
                    },
                  ]}
                  reason={verdictReason(assessment.strength, assessment.reason)}
                  note={verdictNote(assessment.strength)}
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
                    ...(precedentMeta.outcome
                      ? [{ tone: precedentMeta.tone, text: precedentMeta.outcome }]
                      : []),
                  ]}
                  reason={verdictReason(precedent.precedent, precedent.reason)}
                  note={verdictNote(precedent.precedent)}
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
  return (
    <section>
      <div className="flex flex-wrap items-baseline justify-between gap-x-4">
        <SectionLabel>Target stated in document</SectionLabel>
        {rows.length === 0 && <DocumentSourceTrace blockIds={blockIds} />}
      </div>
      <div className="divide-y divide-border/60">
        {rows.map((row, index) =>
          row.kind === "table" ? (
            <div
              key={index}
              /* The first cell names the row, so it is narrower; the rest are the document's
                 values. A fixed trailing column for the trigger: sharing the last cell left
                 it fighting the longest text on the row, so its label broke across two lines.
                 `items-start`, so the trigger sits on the row's first line. */
              style={{ "--values": Math.max(row.cells.length - 1, 1) } as CSSProperties}
              className="grid items-start gap-x-4 gap-y-1 py-2 sm:grid-cols-[minmax(0,0.8fr)_repeat(var(--values),minmax(0,1.6fr))_7rem]"
            >
              {row.cells.map((cell, cellIndex) => (
                <div key={cellIndex} className="min-w-0">
                  {/* The column's own title line - "Minimum", not the guidance under it - with
                      the whole heading a hover away. On every row rather than once above the
                      table, because rows from one field can come from different tables. */}
                  <p className="truncate text-[11px] leading-5 text-muted-foreground" title={cell.header}>
                    {cell.label}
                  </p>
                  {cellIndex === 0 ? (
                    <p className="text-xs font-medium text-foreground">{cell.value || "—"}</p>
                  ) : (
                    <Quoted size="prominent" className="mt-0">{cell.value || "—"}</Quoted>
                  )}
                </div>
              ))}
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
              className="flex flex-col items-start justify-between gap-3 py-2 sm:flex-row"
            >
              {/* The document's own words, so ruled. It rendered as plain prose here and
                  as a quote in the trace panel that opens from it - the same text, two
                  treatments, one of them saying nothing about where it came from. */}
              <div className="min-w-0 flex-1">
                <Quoted collapsible size="prominent" className="mt-0">{row.text}</Quoted>
              </div>
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
  const targetLabel = conformityTargetLabel(conformity, target);
  const dimensions = target ? comparisonDimensions(target) : [];
  const formatBenchmark = (value: number | null) =>
    formatMeasure(value, conformity.unit, target?.expression.display);
  const coverageLabel = CALIBRATION_BASIS_LABEL[conformity.calibration_status];
  const targetRoleLabel = TARGET_ROLE_LABEL[conformity.target_role];
  const view = calibrationView(conformity, target?.expression.display);
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
      <summary className="flex cursor-pointer select-none flex-wrap items-baseline gap-x-3 gap-y-2 outline-none focus-visible:ring-2 focus-visible:ring-ring/60 [&::-webkit-details-marker]:hidden">
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
        <span className="flex w-full flex-wrap items-center justify-end gap-1 self-start lg:w-auto">
          <ComparatorCohort conformity={conformity} matches={matches} target={target} />
          <ExcludedMeasurements conformity={conformity} matches={matches} target={target} />
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
          <Quoted collapsible size="prominent" className="mt-1.5">
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
                  <TargetQualifierSource target={target} dimension={dimension} />
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
                        target?.expression.display,
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
                    target?.expression.display,
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
  note = "",
  citations,
  fallback,
}: {
  label: string;
  chips: { tone: Tone; text: string }[];
  reason: string;
  /** The interface's own sentence where code recorded the state and no model wrote a reason. */
  note?: string;
  citations: { label?: string; cited: Citation }[];
  /** Drawn only when nothing the ids named could be found; see `needsFindingFallback`. */
  fallback: Finding[];
}) {
  const orphaned = citations.every((entry) =>
    needsFindingFallback(entry.cited),
  );
  return (
    <section className="border-t border-border/60 py-5 first:border-t-0 first:pt-0">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <SectionLabel>{label}</SectionLabel>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
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
      {note && <InterfaceNote className="mt-1.5">{note}</InterfaceNote>}
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
          {/* The relation is named, not only coloured: a bare dot left a reader to work out
              that green meant "Supports" from a section further down. A fixed-width label
              column, as Aligner's rows lead with their document, keeps every sentence on one
              edge and matches the "● Supports 9" groups below. */}
          <a
            href={`#${insightAnchor(match) ?? ""}`}
            onClick={() => revealInsight(insightAnchor(match) ?? "")}
            className="grid grid-cols-[6rem_minmax(0,1fr)] items-baseline gap-x-2 rounded text-xs leading-relaxed text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/60 motion-reduce:transition-none"
          >
            <span className="inline-flex items-center gap-1.5 text-[11px] font-medium text-foreground">
              <ToneDot tone={RELATIONSHIP_TONE[match.relation]} />
              {RELATIONSHIP_LABEL[match.relation]}
            </span>
            <Reading size="prominent" className="mt-0 min-w-0">
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
                  {match.reason && verdictReason(match.relation, match.reason) && <Reading continued>{match.reason}</Reading>}
                  {/* Both directions of provenance, both behind a click and neither
                      expanded by default. Rendering every source inline put 1,121 finding
                      rows on one run in front of the statements they support. */}
                  <div className={cn("mt-1 flex flex-wrap items-center gap-1", TRIGGER_AT_LINE_START)}>
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
      <ConfigSectionHeading>Document selection</ConfigSectionHeading>
      <SourceTypeField
        value={sourceType}
        onChange={(value) => setHeader({ source_type: value })}
      />
      <ConfigSectionHeading>Run options</ConfigSectionHeading>
      <ConfigField
        label="Published since (optional)"
        help="Sources that support date filtering receive this bound directly, changing what they retrieve and rank. Older dated evidence is excluded from the run's counts and benchmarks."
        note={
          <ConfigHelp>
            Undated sources are still included.
          </ConfigHelp>
        }
      >
        <ConfigDateInput
          value={publishedSince}
          onChange={onPublishedSinceChange}
          max={new Date().toISOString().slice(0, 10)}
        />
      </ConfigField>
    </ConfigurationShell>
  );
}
