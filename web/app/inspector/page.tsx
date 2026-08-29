"use client";

import { ResultLayout } from "@/components/ui/result-layout";
import { MetricsRow } from "@/components/ui/metrics-row";
import {
  ResultToolbar,
  ResultToolbarEnd,
} from "@/components/ui/result-toolbar";
import { ResultSearch } from "@/components/ui/result-search";
import { useTraceFocus } from "@/lib/trace-focus";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { CollapsibleCard } from "@/components/collapsible-card";
import { EmptyState } from "@/components/empty-state";
import { VerdictCounts } from "@/components/ui/verdict-counts";
import { VerdictPill } from "@/components/ui/verdict-pill";
import { ErrorMessage } from "@/components/ui/error-message";
import { ConfigurationFields } from "@/components/configuration-fields";
import {
  DocumentSourceProvider,
  DocumentSourceTrace,
} from "@/components/document-source-trace";
import { FinalResultActions } from "@/components/final-result-actions";
import { HeaderGuard } from "@/components/header-guard";
import { InspectorSignalHelp } from "@/components/inspector-signal-help";
import { InspectorDocumentTrace } from "@/components/inspector-document-trace";
import { PriorityPanel } from "@/components/ui/priority-panel";
import { SectionHeading } from "@/components/ui/section-heading";
import { Reading } from "@/components/ui/evidence-text";
import { inspectorAnnotationId } from "@/lib/inspector-document-trace";
import { PageHeader } from "@/components/page-header";
import { RunPanel } from "@/components/run-panel";
import { RunHistory } from "@/components/run-history";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  ASSESSED_VERDICTS,
  VERDICTS,
  VERDICT_DESCRIPTION,
  VERDICT_LABEL,
  runInspector,
  sectionShortfalls,
  worklist,
  type Assessment,
  type Header,
  type InspectionResult,
  type InspectorResponse,
  type SectionAssessment,
  type Verdict,
} from "@/lib/api";
import {
  inspectorResultFilename,
  isInspectorResultFinal,
  packInspectorResult,
  runLabel,
  runScope,
  splitResultContext,
  unpackInspectorResult,
  readResultIdentity,
} from "@/lib/result-file";
import {
  INSPECTOR_EMPTY_MESSAGE,
  INSPECTOR_ORDER_NOTE,
  selectInspectorPriorities,
} from "@/lib/inspector-priorities";
import {
  IMPORT_LIMIT_MESSAGE,
  MAX_RESULTS_PER_TOOL,
  RESULT_LIMIT_MESSAGE,
  useInspectorSession,
} from "@/lib/session";
import { usePriorityDigest } from "@/lib/priority-digest";
import { toolAuthority } from "@/lib/tools";
import { TONE_TEXT, type Tone } from "@/lib/tone";
import { cn } from "@/lib/utils";

const INSPECTOR_STEPS = [
  { key: "parse", label: "Parsing document" },
  { key: "label", label: "Mapping rubric sections" },
  { key: "assess", label: "Assessing rubric units" },
  { key: "consistency", label: "Checking cross-section consistency" },
];

export default function InspectorPage() {
  return (
    <>
      <PageHeader
        title="Inspector"
        description="One document against its rubric: whether it states what the template asks for, usably. Completeness, not correctness — what a shortfall costs a programme is not something Inspector can see."
      />
      <HeaderGuard>
        {(header, ready) => (
          <InspectorView header={header as Header} ready={ready} />
        )}
      </HeaderGuard>
    </>
  );
}

function InspectorView({ header, ready }: { header: Header; ready: boolean }) {
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
  } = useInspectorSession();
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
      const response = await runInspector(
        file,
        header,
        (nextStage, nextProgress) => {
          setStage(nextStage);
          setProgress(nextProgress ?? null);
        },
      );
      addResult(response);
    } catch (runError) {
      setError((runError as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function handleImport(file: File) {
    setError(null);
    if (results.length >= MAX_RESULTS_PER_TOOL) {
      setError(IMPORT_LIMIT_MESSAGE);
      return;
    }
    try {
      const raw = JSON.parse(await file.text());
      const parsed = unpackInspectorResult(raw);
      if (!parsed?.inspection || !Array.isArray(parsed.inspection.sections)) {
        throw new Error("not an Inspector result file");
      }
      setStage(null);
      setProgress(null);
      addResult(parsed, readResultIdentity(raw));
    } catch (importError) {
      setError(`Could not import result: ${(importError as Error).message}`);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      {(!result || showRunPanel) && (
        <RunPanel
          configuration={<ConfigurationFields />}
          busy={busy}
          onRun={(files) => handleRun(files.document)}
          steps={INSPECTOR_STEPS}
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
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (file) handleImport(file);
                  event.target.value = "";
                }}
              />
            </div>
          }
        />
      )}
      {error && <ErrorMessage>{error}</ErrorMessage>}
      {result && (
        <InspectionResultView
          result={result}
          onNewAnalysis={() => setShowRunPanel(true)}
        />
      )}
    </div>
  );
}

function InspectionResultView({
  result,
  onNewAnalysis,
}: {
  result: InspectorResponse;
  onNewAnalysis: () => void;
}) {
  const { results, selectedId, selectResult, removeResult } =
    useInspectorSession();
  const inspection = result.inspection;
  const final = isInspectorResultFinal(result);
  const [resultTab, setResultTab] = useState("trace");
  const revealTrace = useCallback(() => setResultTab("trace"), []);
  const {
    focus: traceFocus,
    open: openBlockInTrace,
    consume: consumeTraceFocus,
  } = useTraceFocus(revealTrace);

  // Lifted with the panel it feeds. Priorities describe the run, so they are read once
  // here rather than inside whichever tab happened to render them.
  const priorityItems = useMemo(
    () => selectInspectorPriorities(inspection),
    [inspection],
  );
  // `selectedId` already came from the session destructure above; the panel's old home
  // read it separately because it sat further down the tree.
  const digest = usePriorityDigest(
    selectedId
      ? {
          resultId: selectedId,
          // The tool's own catalog sentence, so nothing here restates its authority.
          authority: toolAuthority("inspector"),
          orderNote: INSPECTOR_ORDER_NOTE,
          items: priorityItems,
          analysis: splitResultContext(inspection).analysis,
          blockIds: (inspection.blocks ?? []).map((block) => block.id),
          org: inspection.org ?? "",
          interventionClass: inspection.intervention_class ?? "",
          indication: inspection.indication ?? "",
        }
      : null,
  );

  const findings = worklist(inspection);
  const sections = inspection.sections ?? [];
  const conflicts = inspection.document_findings?.length ?? 0;
  // Scope, and only scope: what was examined, and what kind of run it was. The two
  // outcome figures that used to end this line - findings, and cross-section conflicts -
  // moved to the figure row below, where every other tool states how its run came out.
  // Written to the same grammar as Aligner's and Screener's: size, then class, then what
  // was read, so the line under the run's name says the same kind of thing in all four.

  return (
    <ResultLayout
      // The identity the run picker and the download filename already use, so a run is
      // called one thing in all three places.
      title={runLabel(result, "inspector")}
      subtitle={runScope(result, "inspector")}
      metrics={
        <RunCoverage sections={sections} conflicts={conflicts} />
      }
      // The row sums to the unit count, because a unit carries exactly one verdict.
      // Conflicts stand apart from it: one belongs to no unit at all.
      metricsNote="Every rubric unit by verdict, so the row sums to the number of units the rubric asks about. Cross-section conflicts are counted separately, because a conflict belongs to no single unit."

      tabValue={resultTab}
      onTabChange={setResultTab}
      tabs={
        <>
          {/* The document is what Inspector is about, so it opens on the
              document. Scout opens on its evidence for the same reason. */}
          <TabsTrigger value="trace">Documents</TabsTrigger>
          <TabsTrigger value="sections">Sections</TabsTrigger>
          <TabsTrigger value="consistency">Consistency</TabsTrigger>
        </>
      }
      priorities={{
        // Every item links to a rubric unit, so it shows where the sections are.
        tab: "sections",
        panel: (
          <PriorityPanel
            attribution="by Inspector"
            items={priorityItems}
            emptyMessage={INSPECTOR_EMPTY_MESSAGE}
            orderNote={INSPECTOR_ORDER_NOTE}
            digest={
              digest?.state === "ready" ? digest.digest.digest : undefined
            }
            nominations={
              digest?.state === "ready" ? digest.digest.nominations : []
            }
            digestLoading={digest?.state === "loading"}
            digestError={digest?.state === "failed" ? digest.reason : undefined}
          />
        ),
      }}
      actions={
        <>
          <RunHistory
            runs={results}
            selectedId={selectedId}
            onSelect={selectResult}
            onRemove={removeResult}
            label={(value) => runLabel(value, "inspector")}
          />
          <FinalResultActions
            onNewAnalysis={onNewAnalysis}
            download={
              final
                ? {
                    filename: inspectorResultFilename(result),
                    data: packInspectorResult(result),
                  }
                : undefined
            }
          />
        </>
      }
    >
      {!final && (
        <div
          className={cn(
            "border-b border-border bg-[hsl(var(--tone-warning))]/[0.06] px-5 py-3 text-sm sm:px-6",
            TONE_TEXT.warning,
          )}
        >
          This assessment is incomplete. Complete the analysis before
          downloading a final result.
        </div>
      )}
      <DocumentSourceProvider
        blocks={inspection.blocks}
        onOpenInTrace={openBlockInTrace}
      >
        <TabsContent value="trace" className="m-0">
          <InspectorDocumentTrace
            result={inspection}
            focus={traceFocus}
            onFocusConsumed={consumeTraceFocus}
          />
        </TabsContent>
        <TabsContent value="sections" className="m-0">
          <SectionsList sections={sections} inspection={inspection} />
        </TabsContent>
        <TabsContent value="consistency" className="m-0">
          {/* The view's name on the left, because there is nothing here to filter: three
                conflicts do not need a search, and a band holding only its right-hand end
                reads as an empty strip. This also stops the heading below being a second
                copy of the same sentence. */}
          <ResultToolbar>
            <p className="min-w-0 flex-1 text-xs font-medium text-foreground">
              Cross-section conflicts
            </p>
            {/* No count. This band does not filter, and the run's figure row above
                  already states how many cross-section conflicts there are. */}
            <ResultToolbarEnd>
              <InspectorSignalHelp />
            </ResultToolbarEnd>
          </ResultToolbar>
          <div className="px-5 py-5 sm:px-6 sm:py-6">
            <ConsistencyView
              findings={inspection.document_findings ?? []}
              status={inspection.consistency_status}
            />
          </div>
        </TabsContent>
      </DocumentSourceProvider>
    </ResultLayout>
  );
}

function SectionsList({
  sections,
  inspection,
}: {
  sections: SectionAssessment[];
  inspection: InspectionResult;
}) {
  const [query, setQuery] = useState("");
  const normalizedQuery = query.trim().toLowerCase();
  // Matched on a section and on the units inside it, because a reader looking for
  // "Efficacy" is looking for a unit and does not know which section holds it.
  const visible = sections.filter(
    (section) =>
      !normalizedQuery ||
      section.section_name.toLowerCase().includes(normalizedQuery) ||
      section.units.some((unit) =>
        (unit.variable_name ?? section.section_name)
          .toLowerCase()
          .includes(normalizedQuery),
      ),
  );

  return (
    <>
      {/* Chrome first, then content. The search is on the left where Scout and Aligner put
          theirs; without it this band held only its right-hand end and read as an empty
          strip. */}
      <ResultToolbar>
        <ResultSearch
          label="Search sections and units"
          placeholder="Find a section or unit…"
          value={query}
          onChange={setQuery}
        />
        <ResultToolbarEnd
          count={{ shown: visible.length, total: sections.length }}
        >
          <InspectorSignalHelp />
        </ResultToolbarEnd>
      </ResultToolbar>
      <div className="px-5 py-5 sm:px-6 sm:py-6">
        <div className="space-y-3">
          {/* Under the nav, like Consistency's. It says the one thing the rows cannot: that
            opening a section shows *every* unit the rubric asks about, not only the ones
            that produced a finding. */}
          <p className="text-xs leading-5 text-muted-foreground">
            Open a section to see every unit the rubric asks about, its
            findings, and the passages behind them.
          </p>
          {visible.map((section) => (
            <SectionCard key={section.section_name} section={section} />
          ))}
          {visible.length === 0 && (
            <EmptyState message="No section or unit matches that search" />
          )}
        </div>
      </div>
    </>
  );
}

/**
 * One assessment, as a row: what it is about, how it stands, and why.
 *
 * The same renderer for a rubric unit and for a cross-section conflict, because since
 * the vocabulary collapsed they are the same shape - one verdict, one sentence, and the
 * blocks it was read from. Two renderers for one type is two things to keep in step.
 *
 * Flat, which is the change. A unit used to open: the row carried a chevron and the
 * sentence sat behind it under a tinted body. That was right when a unit held several
 * findings, each with a reason, a statement, a recommendation and a trigger - a
 * thirteen-unit section was sixty lines and adjacent rows differed in height ninefold.
 * A unit now holds one verdict and one sentence of at most twenty words, so the
 * disclosure hid two lines behind a click and a reader had to make thirty-two of them
 * to read the assessment. A sound unit is one line; a unit with a problem is three.
 *
 * The section above is still a disclosure, and that is the one that earns it: opening a
 * section is choosing what to read, and there are six of them rather than thirty-two.
 */
function AssessmentRow({
  item,
  title,
}: {
  item: Assessment;
  /** What this is about. The section's name where a unit declares no variable. */
  title: string;
}) {
  return (
    <div className="px-5 py-3.5 sm:px-6">
      <div className="flex items-baseline gap-4">
        <p className="min-w-0 flex-1 truncate text-sm font-medium">{title}</p>
        <div className="flex shrink-0 items-center gap-2">
          {/* Muted text, not a second pill. `Optional` is the rubric author's decision
              about this unit, not a verdict about the document, and two pills on one row
              read as two judgements. */}
          {item.optional && (
            <span className="text-[11px] text-muted-foreground">Optional</span>
          )}
          <StatusPill status={item.verdict} />
        </div>
      </div>
      {/* The verdict is on the pill and nowhere else. It used to be repeated here as
          well, which made sense when a unit held several findings and each carried its
          own reason; with one verdict per unit the second copy says nothing. */}
      {item.statement && (
        <Reading size="prominent" className="mt-1 pr-16">
          {item.statement}
        </Reading>
      )}
      {item.cited_block_ids.length > 0 && (
        <div className="mt-1.5">
          {/* Named, so the trace opens on this unit's own layer rather than on every
              layer the passage carries. */}
          <DocumentSourceTrace
            blockIds={item.cited_block_ids}
            annotationId={inspectorAnnotationId(item.id)}
          />
        </div>
      )}
    </div>
  );
}

function SectionCard({ section }: { section: SectionAssessment }) {
  return (
    <CollapsibleCard
      title={section.section_name}
      subtitle={section.is_present ? undefined : "Required section not found"}
      trailing={<ShortfallCounts section={section} />}
      defaultOpen={false}
    >
      {/* Dividers, not a second bordered box. The card already draws the boundary; a
          rounded border inside a rounded border was the third nesting level on a page
          Scout renders with two. */}
      <div className="divide-y divide-border/60">
        {section.units.map((unit) => (
          <AssessmentRow
            key={unit.variable_name ?? section.section_name}
            item={unit}
            title={unit.variable_name ?? section.section_name}
          />
        ))}
      </div>
    </CollapsibleCard>
  );
}

/**
 * How the run came out, in figures that hold on every tab.
 *
 * Inspector was the only tool with no figure row. Its outcome lived in the subtitle as
 * "18 findings · 3 cross-section conflicts" - true, but plain text where the other three
 * show graded counts, so the one tool whose whole job is grading a document was the one
 * that showed no grade above the fold.
 *
 * Every status, including zeros, which is the opposite of `ShortfallCounts` one level
 * down and deliberate for the same reason Aligner shows all of its verdicts: the
 * denominator here is the whole rubric, so a zero says the class was checked and nothing
 * fell into it. A zero on one *section* says nothing, because that section may not have
 * been asked.
 *
 * Findings and conflicts are counted apart from the statuses rather than beside them.
 * They are a different denominator - one unit can carry several findings, and a
 * cross-section conflict belongs to no unit at all - so standing in the same row they
 * would read as a fifth and sixth status and break the rule that the row sums to the
 * unit count.
 */
function RunCoverage({
  sections,
  conflicts,
}: {
  sections: SectionAssessment[];
  conflicts: number;
}) {
  const counts = VERDICTS.reduce(
    (totals, verdict) => {
      totals[verdict] = sections.reduce(
        (sum, section) => sum + (section.verdict_counts?.[verdict] ?? 0),
        0,
      );
      return totals;
    },
    {} as Record<Verdict, number>,
  );

  const unitTotal = sections.reduce((sum, section) => sum + section.units.length, 0);

  // A conflict belongs to no unit, so it is not one of them. Everything else on this
  // row is a unit and the row sums to the unit count.
  const unitVerdicts = VERDICTS.filter((verdict) => verdict !== "section_conflict");

  return (
    <MetricsRow
      total={unitTotal}
      unit={["unit", "units"]}
      items={unitVerdicts.map((verdict) => ({
        label: VERDICT_LABEL[verdict],
        count: counts[verdict],
        tone: VERDICT_TONE[verdict],
      }))}
      aside={
        conflicts > 0 && (
          <p className="text-[11px] tabular-nums text-muted-foreground">
            {conflicts} cross-section {conflicts === 1 ? "conflict" : "conflicts"}
          </p>
        )
      }
    />
  );
}

/**
 * A section's units that fall short, by level.
 *
 * A zero says nothing, so it is not shown: on a six-section rubric most of these
 * were "0" and the eye had to sort twelve numbers to find the two that mattered.
 * The counts are of units, so they are bounded by the rubric rather than by how
 * much the model had to say.
 */
function ShortfallCounts({ section }: { section: SectionAssessment }) {
  const counts = sectionShortfalls(section);
  const shown = ASSESSED_VERDICTS.filter((verdict) => counts[verdict] > 0);
  if (shown.length === 0) {
    // The same pill a unit shows. One signal, and it is what this row is about, so it is a
    // tint - the rule in `lib/tone.ts`. It rendered as muted text here and as a pill one
    // level down, so one verdict had two appearances on one screen.
    return <StatusPill status="specified" />;
  }
  // A zero is hidden here on purpose: a shortfall that did not occur is not a fact about
  // the document. Screener shows its zeros for the opposite and equally deliberate reason.
  return (
    <VerdictCounts
      items={shown.map((verdict) => ({
        // One vocabulary, so the section header and the unit pill it summarises read
        // the same word from the same map and cannot disagree about it.
        label: VERDICT_LABEL[verdict],
        count: counts[verdict],
        tone: VERDICT_TONE[verdict],
      }))}
    />
  );
}

function ConsistencyView({
  findings,
  status,
}: {
  findings: Assessment[];
  status: InspectionResult["consistency_status"];
}) {
  if (findings.length === 0) {
    const complete = status === "complete" || status === "not_applicable";
    // Two answers, not one absence. A check that ran and found nothing is good news; a
    // check that did not finish is a question still open, and a reader who cannot tell
    // them apart cannot tell a clean document from an unread one.
    return (
      <EmptyState
        tone={complete ? "clear" : "unknown"}
        message={
          complete
            ? "No cross-section conflicts identified"
            : "Consistency coverage is incomplete"
        }
        detail={consistencyDescription(status)}
      />
    );
  }
  return (
    <div>
      {/* The count and the name are in the toolbar above; what is left is the one thing a
          reader cannot see, which is how much of the document the pass actually covered. */}
      <p className="border-b border-border/60 px-5 py-3 text-xs leading-5 text-muted-foreground sm:px-6">
        {consistencyDescription(status)}
      </p>
      {/* The same rows the Sections tab shows, in the same divided list. A conflict is
          the same shape as a unit - one verdict, one sentence, the blocks it was read
          from - and it used to render as a bordered card instead, so the same kind of
          claim looked like a different kind of thing depending on the tab. */}
      <div className="divide-y divide-border/60">
        {findings.map((finding) => (
          <AssessmentRow
            key={finding.id}
            item={finding}
            title={conflictTitle(finding)}
          />
        ))}
      </div>
    </div>
  );
}

/**
 * What to call a conflict, which belongs to no unit.
 *
 * Titled by the sections its own citations resolve to, the same derivation the document
 * trace uses. Naming them a second way here would be a second answer to "which sections
 * disagree" that could differ from the one in the gutter.
 */
function conflictTitle(finding: Assessment): string {
  return finding.variable_name ?? finding.section_name ?? "Across sections";
}

function consistencyDescription(
  status: InspectionResult["consistency_status"],
): string {
  if (status === "complete")
    return "The complete retained document context was checked across mapped sections.";
  if (status === "partial")
    return "The document exceeded the full-pass context bound; findings reflect the retained section-balanced context.";
  if (status === "failed")
    return "The consistency pass did not complete; every section assessment above is unaffected.";
  if (status === "not_applicable")
    return "Fewer than two mapped sections were available for a cross-section comparison.";
  return "This saved result does not record consistency-pass completion.";
}

function StatusPill({ status }: { status: Verdict }) {
  // No help affordance. The verdicts are told apart by contrast, so an icon on one of
  // them cannot do the job: it says what "Insufficient" is without saying how it differs
  // from "Vague", which is the thing a reader gets wrong. "How to read" shows them
  // together and is the only place they are explained. Scout reached the same conclusion
  // for the same reason; the native title stays, because it costs nothing and adds no
  // mark to the page.
  return (
    <VerdictPill
      label={VERDICT_LABEL[status]}
      tone={VERDICT_TONE[status]}
      description={VERDICT_DESCRIPTION[status]}
    />
  );
}

/* The short forms live in `lib/api.ts` as `VERDICT_LABEL`. They used to live here, so the
   document trace could not reach them and rendered the description as pill text instead.
   Colour is decided once here as a tone and applied by `VerdictPill`. */

/**
 * One tone per verdict. The only place the judgement is made.
 *
 * The pill fills with it and the section's count row dots with it - two shapes, one
 * decision, per the rule in `lib/tone.ts`. Two maps here would be the same verdict decided
 * twice, which is how a status came to be one colour on a unit and another on the section
 * summarising it.
 *
 * The shortfalls are not graded against each other. `vague` is the one that leaves the
 * requirement covered - the content is all there and unusable - so it reads as caution;
 * the rest leave something absent and read as danger. That split is the vocabulary's own
 * worst-first order, not a severity scale invented here.
 */
const VERDICT_TONE: Record<Verdict, Tone> = {
  specified: "success",
  not_present: "danger",
  placeholder: "danger",
  insufficient: "danger",
  vague: "warning",
  section_conflict: "danger",
  not_applicable: "neutral",
};

/* The tint is applied by `VerdictPill`, which reads the tone directly. A map from
   verdict to class lived here as well, which is one lookup more than the fact needs. */
