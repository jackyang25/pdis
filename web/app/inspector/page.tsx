"use client";

import { ChevronDown } from "lucide-react";
import { ResultLayout } from "@/components/ui/result-layout";
import {
  ResultToolbar,
  ResultToolbarEnd,
} from "@/components/ui/result-toolbar";
import { ResultSearch } from "@/components/ui/result-search";
import { EXPANDABLE_ROW } from "@/lib/expandable-row";
import { DISCLOSURE_MOTION } from "@/lib/motion";
import { SURFACE } from "@/lib/surface";
import { useTraceFocus } from "@/lib/trace-focus";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { CollapsibleCard } from "@/components/collapsible-card";
import { EmptyState } from "@/components/empty-state";
import { VerdictCounts } from "@/components/ui/verdict-counts";
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
import { LabeledItem } from "@/components/labeled-item";
import { inspectorAnnotationId } from "@/lib/inspector-document-trace";
import { PageHeader } from "@/components/page-header";
import { RunPanel } from "@/components/run-panel";
import { RunHistory } from "@/components/run-history";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  LEVEL_LABELS,
  REASON_DESCRIPTION,
  REASON_LABELS,
  SECTION_SHORTFALLS,
  STATUS_DESCRIPTION,
  STATUS_LABEL,
  UNIT_STATUSES,
  runInspector,
  sectionShortfalls,
  worklist,
  type FindingLevel,
  type Header,
  type InspectionResult,
  type InspectorResponse,
  type RubricFinding,
  type SectionAssessment,
  type UnitAssessment,
  type UnitStatus,
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
import { TONE_TEXT, TONE_TINT, type Tone } from "@/lib/tone";
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
        description="One document against its rubric: every unit the rubric asks about, and every finding tied to the passage it came from."
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
  // Written to the same grammar as Aligner's and Expert's: size, then class, then what
  // was read, so the line under the run's name says the same kind of thing in all four.

  return (
    <ResultLayout
      // The identity the run picker and the download filename already use, so a run is
      // called one thing in all three places.
      title={runLabel(result, "inspector")}
      subtitle={runScope(result, "inspector")}
      metrics={
        <RunCoverage
          sections={sections}
          findings={findings}
          conflicts={conflicts}
        />
      }
      // Two denominators. The statuses are units and sum to the unit count; findings and
      // conflicts do not, because one unit can carry several and a cross-section conflict
      // belongs to no unit at all.
      metricsNote="Every rubric unit by status, then what the run found. A unit can carry several findings, and a cross-section conflict belongs to no unit, so the two do not sum to each other."

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
 * Whether a finding's prose only repeats the fields rendered beside it.
 *
 * True for exactly one case, and deliberately narrow. A *variable* the document never
 * wrote has both sentences built from its own name, its section's name, and its reason -
 * all three already on the row. A *section* that declares no variables does not qualify:
 * its recommendation carries the rubric's description of what that section should cover,
 * which appears nowhere else on screen.
 */
function restatesItself(finding: RubricFinding): boolean {
  return finding.reason === "missing" && Boolean(finding.variable_name);
}

/**
 * One finding, rendered the same way wherever it appears.
 *
 * The section list and the findings list show the same object, so they share one
 * renderer; two would be two things to keep in step.
 */
function FindingBody({
  finding,
  showUnit = true,
}: {
  finding: RubricFinding;
  showUnit?: boolean;
}) {
  return (
    <div className="min-w-0 flex-1">
      <p className="flex flex-wrap items-baseline gap-x-1.5">
        {showUnit && (
          <span className="font-medium">
            {finding.variable_name ?? finding.section_name ?? "Across sections"}
          </span>
        )}
        {/* Plain, like every other reason on the page. The vocabulary is explained once
            in "How to read", which is the only place that can show a reason beside the
            five it is not - and this line repeats 32 times in a run. */}
        {/* Short, with the full sentence on hover. The panel explains all six together,
            which is the only place they can be told apart from each other. */}
        <span
          className="text-xs text-muted-foreground"
          title={REASON_DESCRIPTION[finding.reason]}
        >
          {REASON_LABELS[finding.reason]}
        </span>
      </p>
      {/* Both sentences are the model's, so both are `Reading`. They used to render at
          two contrasts in one card - the statement at full, the recommendation muted -
          which told a reader the two had different authors when they have the same one.
          Full contrast belongs to the tool's own words and the document's values, and the
          lede of this card is the unit name and its verdict, both of which are the tool's.
          Hierarchy between the two comes from size, which is what `Reading` sizes are for.

          Suppressed when the finding restates itself. A variable the document never wrote
          gets both sentences templated in `assembly.py` out of the three fields already on
          this row - the unit name, the section, and the reason - so "Target User Group is
          not present; the Medical Need / Use Case section is absent" and "Add the Medical
          Need / Use Case section and state Target User Group" carry nothing the row has
          not said. On a six-variable section that was one fact rendered twenty-five times.

          They stay in the result: a JSON consumer without the rubric cannot rebuild the
          sentence, and the assistant reads that JSON. This is a rendering decision, not a
          data one - and it is also an authorship correction, because template text was
          being shown in the treatment that means a model judged it. */}
      {!restatesItself(finding) && (
        <>
          <Reading size="prominent">{finding.statement}</Reading>
          {finding.recommendation && (
            <Reading>{finding.recommendation}</Reading>
          )}
        </>
      )}
      {finding.cited_block_ids.length > 0 && (
        <div className="mt-1.5">
          {/* Named, so the trace opens on this finding's own layer rather than on
              every layer the passage carries. */}
          <DocumentSourceTrace
            blockIds={finding.cited_block_ids}
            annotationId={inspectorAnnotationId(finding.id)}
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
          <UnitRow
            key={unit.variable_name ?? section.section_name}
            unit={unit}
            sectionName={section.section_name}
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
  findings,
  conflicts,
}: {
  sections: SectionAssessment[];
  findings: RubricFinding[];
  conflicts: number;
}) {
  const counts = UNIT_STATUSES.reduce(
    (totals, status) => {
      totals[status] = sections.reduce(
        (sum, section) => sum + (section.status_counts?.[status] ?? 0),
        0,
      );
      return totals;
    },
    {} as Record<UnitStatus, number>,
  );

  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
      <VerdictCounts
        items={UNIT_STATUSES.map((status) => ({
          label: STATUS_LABEL[status],
          count: counts[status],
          tone: STATUS_TONE[status],
        }))}
      />
      <span className="text-[11px] tabular-nums text-muted-foreground">
        {findings.length} {findings.length === 1 ? "finding" : "findings"}
        {conflicts > 0 && (
          <>
            {" · "}
            {conflicts} cross-section{" "}
            {conflicts === 1 ? "conflict" : "conflicts"}
          </>
        )}
      </span>
    </div>
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
  const shown = SECTION_SHORTFALLS.filter((status) => counts[status] > 0);
  if (shown.length === 0) {
    // The same pill a unit shows. One signal, and it is what this row is about, so it is a
    // tint - the rule in `lib/tone.ts`. "Met" rendered as muted text here and as a pill one
    // level down, so one verdict had two appearances on one screen.
    return <StatusPill status="met" />;
  }
  // A zero is hidden here on purpose: a shortfall that did not occur is not a fact about
  // the document. Expert shows its zeros for the opposite and equally deliberate reason.
  return (
    <VerdictCounts
      items={shown.map((status) => ({
        // The unit vocabulary, because these are units. Reading `STATUS_LABEL` rather
        // than the finding-level copy also means the section header and the unit pill it
        // summarises can never disagree about a word.
        label: STATUS_LABEL[status],
        count: counts[status],
        tone: STATUS_TONE[status],
      }))}
    />
  );
}

/**
 * One rubric unit: its name, its verdict, and its findings behind a disclosure.
 *
 * Collapsed, which is the change. Every unit used to render all of its findings inline -
 * each with a reason, a statement, a recommendation and a provenance trigger - so a
 * thirteen-unit section was sixty lines and adjacent rows differed in height by a factor of
 * nine. Scout reads a field beside twenty-seven others and collapses; this reads a unit
 * beside thirty-one and did not.
 *
 * A unit with no findings is not a disclosure at all. There is nothing behind it, and a
 * control that opens to nothing is the same mistake as a citation that resolves to nothing.
 */
function UnitRow({
  unit,
  sectionName,
}: {
  unit: UnitAssessment;
  sectionName: string;
}) {
  const heading = (
    <>
      <p className="min-w-0 flex-1 truncate text-sm font-medium">
        {unit.variable_name ?? sectionName}
      </p>
      <div className="flex shrink-0 items-center gap-2">
        {/* Muted text, not a second pill. `Optional` is the rubric author's decision about
            this unit, not a verdict about the document, and two pills on one row read as
            two judgements. */}
        {unit.optional && (
          <span className="text-[11px] text-muted-foreground">Optional</span>
        )}
        <StatusPill status={unit.status} />
      </div>
    </>
  );

  if (unit.findings.length === 0) {
    return (
      <div className="flex items-center gap-4 px-5 py-4 sm:px-6">{heading}</div>
    );
  }

  return (
    <details className="group/unit">
      <summary className={cn(EXPANDABLE_ROW, "items-center")}>
        <ChevronDown
          className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground transition-transform group-open/unit:rotate-180 motion-reduce:transition-none"
          aria-hidden="true"
        />
        {heading}
      </summary>
      <ul
        className={cn(
          "space-y-2.5 px-5 pb-4 text-sm leading-6 sm:px-6",
          SURFACE.open.body,
          DISCLOSURE_MOTION,
        )}
      >
        {unit.findings.map((finding) => (
          <li key={finding.id}>
            {/* The unit's name is the row heading, so the finding does not
                repeat it here. */}
            <FindingBody finding={finding} showUnit={false} />
          </li>
        ))}
      </ul>
    </details>
  );
}

function ConsistencyView({
  findings,
  status,
}: {
  findings: RubricFinding[];
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
    <div className="space-y-3">
      {/* The count and the name are in the toolbar above; what is left is the one thing a
          reader cannot see, which is how much of the document the pass actually covered. */}
      <p className="text-xs leading-5 text-muted-foreground">
        {consistencyDescription(status)}
      </p>
      {findings.map((finding) => (
        <article
          key={finding.id}
          className="rounded-lg border border-border p-4"
        >
          {/* The model's sentence, like the one in a section card. It was at full
              contrast here and muted there, so the same kind of claim carried two
              authorships depending on which tab you were reading. */}
          <Reading size="prominent">{finding.statement}</Reading>
          {finding.recommendation && (
            <div className="mt-3">
              <LabeledItem kind="recommendation">
                {finding.recommendation}
              </LabeledItem>
            </div>
          )}
          <div className="mt-3">
            {/* Named, so the trace opens on this finding's own layer rather than on
              every layer the passage carries. */}
            <DocumentSourceTrace
              blockIds={finding.cited_block_ids}
              annotationId={inspectorAnnotationId(finding.id)}
            />
          </div>
        </article>
      ))}
    </div>
  );
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

function StatusPill({ status }: { status: UnitStatus }) {
  return (
    // No help affordance. The four statuses are told apart by contrast, so an icon on one
    // of them cannot do the job: it says what "Not met" is without saying how it differs
    // from "Could be stronger", which is the thing a reader gets wrong. "How to read"
    // shows all four together and is the only place they are explained. Scout reached the
    // same conclusion for the same reason; the native title stays, because it costs
    // nothing and adds no mark to the page.
    <span
      title={STATUS_DESCRIPTION[status]}
      className={cn(
        "inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium",
        STATUS_SURFACE[status],
      )}
    >
      {STATUS_LABEL[status]}
    </span>
  );
}

/* The short forms moved to `lib/api.ts` as `STATUS_LABEL`. They lived here, so the document
   trace could not reach them and rendered the description as pill text instead. Colour is
   still a local concern: see `STATUS_SURFACE`. */

// Half of these reached the tone tokens and half wrote the palette out with a hand-kept
// dark-mode variant beside it, for verdicts that sit in the same row as each other.
/**
 * One tone per unit status. The only place the judgement is made.
 *
 * The pill fills with it and the section's count row dots with it - two shapes, one
 * decision, per the rule in `lib/tone.ts`. Two maps here would be the same verdict decided
 * twice, which is how a status came to be one colour on a unit and another on the section
 * summarising it.
 */
const STATUS_TONE: Record<UnitStatus, Tone> = {
  met: "success",
  could_be_stronger: "warning",
  not_met: "danger",
  not_applicable: "neutral",
};

const STATUS_SURFACE: Record<UnitStatus, string> = Object.fromEntries(
  UNIT_STATUSES.map((status) => [status, TONE_TINT[STATUS_TONE[status]]]),
) as Record<UnitStatus, string>;
