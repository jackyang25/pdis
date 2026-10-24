"use client";

import { ResultLayout } from "@/components/ui/result-layout";
import { DocumentExtractionNotice } from "@/components/document-extraction-notice";
import { WarningNotice } from "@/components/ui/warning-notice";
import { matchesQuery, normalizeQuery } from "@/lib/result-search";
import { MetricsRow } from "@/components/ui/metrics-row";
import {
  ResultToolbar,
  ResultToolbarEnd,
} from "@/components/ui/result-toolbar";
import { ResultSearch } from "@/components/ui/result-search";
import { useTraceFocus } from "@/lib/trace-focus";
import { memo, useCallback, useEffect, useMemo, useState } from "react";
import { useShallow } from "zustand/react/shallow";
import { CollapsibleCard } from "@/components/collapsible-card";
import { EmptyState } from "@/components/empty-state";
import { VerdictCounts } from "@/components/ui/verdict-counts";
import { VerdictPill } from "@/components/ui/verdict-pill";
import { SignalChip } from "@/components/ui/signal-chip";
import { ResultCardStack } from "@/components/ui/result-card-stack";
import { ErrorMessage } from "@/components/ui/error-message";
import { ConfigurationFields } from "@/components/configuration-fields";
import { ConfigField, ConfigHelp, ConfigSelect, ConfigSectionHeading } from "@/components/ui/config-field";
import { useInspectorConfiguration } from "@/lib/use-configuration-catalog";
import { projectInspectionReview } from "@/lib/inspector-reviews";
import { InspectorRubricDetails, InspectorRubricOmissions, InspectorRequirement } from "@/components/inspector-rubric-details";
import {
  DocumentSourceProvider,
  DocumentSourceTrace,
} from "@/components/document-source-trace";
import { FinalResultActions } from "@/components/final-result-actions";
import { HeaderGuard } from "@/components/header-guard";
import { InspectorSignalHelp } from "@/components/inspector-signal-help";
import { InspectorDocumentTrace } from "@/components/inspector-document-trace";
import { PriorityPanel } from "@/components/ui/priority-panel";
import { InterfaceNote, Reading } from "@/components/ui/evidence-text";
import { inspectorAnnotationId } from "@/lib/inspector-document-trace";
import { PageHeader } from "@/components/page-header";
import { RunPanel } from "@/components/run-panel";
import { RunHistory } from "@/components/run-history";
import { TabsContent, TabsTrigger } from "@/components/ui/tabs";
import {
  ASSESSED_VERDICTS,
  VERDICTS,
  VERDICT_DESCRIPTION,
  VERDICT_LABEL,
  VERDICT_TONE,
  runInspector,
  sectionShortfalls,
  type Assessment,
  type Header,
  type InspectionResult,
  type RubricSnapshot,
  type RequirementSnapshot,
  type ProductFact,
  type InspectorResponse,
  type SectionAssessment,
  type Verdict,
} from "@/lib/api";
import {
  runFilename,
  isInspectorResultFinal,
  packInspectorResult,
  runLabel,
  runScope,
  unpackInspectorResult,
} from "@/lib/result-file";
import {
  INSPECTOR_PRIORITY_FOCUS,
  inspectorPriorityFindings,
} from "@/lib/inspector-priorities";
import { useInspectorSession } from "@/lib/session";
import { importTool, runTool } from "@/lib/tool-run";
import { usePriorityReading } from "@/lib/priority-reading";
import { toolAuthority } from "@/lib/tools";
import { ROW_TITLE } from "@/lib/typography";
import { cn } from "@/lib/utils";
import { TRIGGER_AT_LINE_START } from "@/components/ui/provenance";

const INSPECTOR_STEPS = [
  { key: "parse", label: "Parsing document" },
  { key: "label", label: "Mapping rubric sections" },
  { key: "assess", label: "Assessing rubric units" },
  { key: "consistency", label: "Checking cross-section consistency" },
];

export default function InspectorPage() {
  return (
    <>
      <PageHeader title="Inspector" description={toolAuthority("inspector")} />
      <HeaderGuard>
        {(header, ready) => (
          <InspectorView header={header as Header} ready={ready} />
        )}
      </HeaderGuard>
    </>
  );
}

function InspectorView({ header, ready }: { header: Header; ready: boolean }) {
  const { result, busy, stage, progress, error, selectedId, startedAt } = useInspectorSession(
    useShallow(({ result, busy, stage, progress, error, selectedId, startedAt }) =>
      ({ result, busy, stage, progress, error, selectedId, startedAt })),
  );
  const [showRunPanel, setShowRunPanel] = useState(!result);
  const catalog = useInspectorConfiguration(header);
  const profileKey = JSON.stringify([header.org, header.source_type, header.intervention_class]);
  const [factState, setFactState] = useState<{ key: string; values: Record<string, ProductFact> }>({ key: profileKey, values: {} });
  const facts = factState.key === profileKey ? factState.values : {};

  useEffect(() => {
    if (result) setShowRunPanel(false);
  }, [result]);

  function handleRun(file: File) {
    const productFacts = Object.fromEntries(
      catalog.fields.map(field => [field.key, facts[field.key] ?? "unknown"]),
    );
    void runTool(useInspectorSession, (report) => runInspector(file, header, report, productFacts));
  }

  const showSetup = useCallback(() => setShowRunPanel(true), []);

  return (
    <div className="flex flex-col gap-6">
      {(busy || !result || showRunPanel) && (
        <RunPanel
            onCancel={result ? () => setShowRunPanel(false) : undefined}
          configuration={<ConfigurationFields>
            {catalog.fields.length > 0 && <>
              <ConfigSectionHeading>Product context</ConfigSectionHeading>
              {catalog.fields.map(field => <ConfigField key={field.key} label={field.label} help={field.description}>
                <ConfigSelect value={facts[field.key] ?? "unknown"} disabled={busy}
                  options={field.options.map(value => ({ value, label: value === "unknown" ? "Not known" : value === "yes" ? "Yes" : "No" }))}
                  onChange={value => setFactState({ key: profileKey, values: { ...facts, [field.key]: value as ProductFact } })} />
              </ConfigField>)}
              <ConfigHelp>Unknown facts leave dependent reviews unassessed. Other applicable reviews still run.</ConfigHelp>
            </>}
            {/* A profile's extra questions arrive a moment after its document type is chosen;
                saying so keeps the rail from looking finished before they do. */}
            {ready && !catalog.ready && !catalog.error && (
              <ConfigHelp>Loading product context…</ConfigHelp>
            )}
            {catalog.error && <ErrorMessage>{catalog.error}</ErrorMessage>}
          </ConfigurationFields>}
          busy={busy}
          startedAt={startedAt}
          onRun={(files) => handleRun(files.document)}
          steps={INSPECTOR_STEPS}
          currentStage={stage}
          progress={progress}
          runDisabled={!ready || !catalog.ready}
          hint={ready ? undefined : "Complete the configuration to run."}
          onImport={(file) => importTool(useInspectorSession, file, unpackInspectorResult)}
        />
      )}
      {error && <ErrorMessage>{error}</ErrorMessage>}
      {result && (
        <InspectionResultView
          key={selectedId}
          result={result}
          onNewAnalysis={showSetup}
        />
      )}
    </div>
  );
}

/** Memoized so a run's progress ticks, which re-render the page, leave a held result alone. */
const InspectionResultView = memo(function InspectionResultView({
  result,
  onNewAnalysis,
}: {
  result: InspectorResponse;
  onNewAnalysis: () => void;
}) {
  const { results, selectedId, selectResult, removeResult } = useInspectorSession(
    useShallow(({ results, selectedId, selectResult, removeResult }) =>
      ({ results, selectedId, selectResult, removeResult })),
  );
  const held = results.find((entry) => entry.id === selectedId);
  const run = result.inspection;
  const [rubricId, setRubricId] = useState(run.reviews[0].rubric.id);
  const inspection = useMemo(() => projectInspectionReview(run, rubricId), [run, rubricId]);
  const final = isInspectorResultFinal(result);
  const [resultTab, setResultTab] = useState("sections");
  const revealTrace = useCallback(() => setResultTab("trace"), []);
  const {
    focus: traceFocus,
    open: openBlockInTrace,
    consume: consumeTraceFocus,
  } = useTraceFocus(revealTrace);

  // The card reads the selected rubric's review, so it is keyed per rubric: a reading of one
  // review must never speak for another.
  const priorityFindings = useMemo(() => inspectorPriorityFindings(inspection), [inspection]);
  const priorityReading = usePriorityReading(
    selectedId ? `${selectedId}:${rubricId}` : null,
    {
      // The tool's own catalog sentence, so nothing here restates its authority.
      authority: `${toolAuthority("inspector")} Selected rubric: ${inspection.rubric.display_name}. ${inspection.rubric.scope}`,
      focus: INSPECTOR_PRIORITY_FOCUS,
      findings: priorityFindings,
      org: inspection.org ?? "",
      interventionClass: inspection.intervention_class ?? "",
      indication: inspection.indication ?? "",
    },
  );

  const sections = inspection.sections ?? [];
  const conflicts = inspection.document_findings?.length ?? 0;
  // Scope, and only scope: what was examined, and what kind of run it was. The two
  // outcome figures that used to end this line - findings, and cross-section conflicts -
  // moved to the figure row below, where every other tool states how its run came out.
  // Written to the same grammar as Aligner's and Screener's: size, then class, then what
  // was read, so the line under the run's name says the same kind of thing in all four.

  return (
    // Around the whole layout, not inside its tabs, so the priority card's source triggers
    // resolve passages too. Inside `children` the card sat outside it and opened nothing.
    <DocumentSourceProvider
      blocks={inspection.blocks}
      onOpenInTrace={openBlockInTrace}
    >
    <ResultLayout
      notices={<>
        {!final && <WarningNotice label="Assessment incomplete">
          This assessment is incomplete. Complete the analysis before downloading a final result.
        </WarningNotice>}
        <DocumentExtractionNotice blocks={inspection.blocks} />
      </>}
      // The identity the run picker and the download filename already use, so a run is
      // called one thing in all three places.
      title={runLabel(result, "inspector")}
      subtitle={runScope(result, "inspector")}
      scopeControl={<div className="space-y-3">
        <div className="w-full max-w-md">
          <ConfigField label="Rubric" help={<InspectorRubricDetails rubric={inspection.rubric} />}
            note={<ConfigHelp>Rubric updated: {inspection.rubric.updated_on ?? "not recorded"}</ConfigHelp>}>
            {/* A picker only when there is a choice. With one rubric it was a dropdown
                holding one option, on every Inspector result. */}
            {run.reviews.length > 1 ? (
              <ConfigSelect value={rubricId} options={run.reviews.map(({ rubric }) => ({ value: rubric.id,
                label: rubricLabel(rubric) }))}
                onChange={value => { if (traceFocus) consumeTraceFocus(traceFocus); setRubricId(value); }} />
            ) : (
              <p className="text-xs font-medium text-foreground">{rubricLabel(inspection.rubric)}</p>
            )}
          </ConfigField>
        </div>
        <InspectorRubricOmissions resolutions={run.rubric_resolutions} />
      </div>}
      metrics={
        <RunCoverage sections={sections} conflicts={conflicts} />
      }
      // The row sums to the unit count, because a unit carries exactly one verdict.
      // Conflicts stand apart from it: one belongs to no unit at all.
      metricsNote={`Units from ${inspection.rubric.display_name}, counted by verdict. Document consistency is checked once for the run, independently of the selected rubric.`}

      tabValue={resultTab}
      onTabChange={setResultTab}
      tabs={
        <>
          {/* Findings first, as in every tool that judges a document: Aligner opens on its
              comparisons, Screener on its questions, Scout on its fields. Opening on the
              document put the priorities card, which lives with the sections, out of sight
              on arrival. */}
          <TabsTrigger value="sections">Sections</TabsTrigger>
          <TabsTrigger value="consistency">Consistency</TabsTrigger>
          <TabsTrigger value="trace">Documents</TabsTrigger>
        </>
      }
      priorities={{
        // Every point rests on rubric units, so it shows where the sections are.
        tab: "sections",
        panel: <PriorityPanel findings={priorityFindings} reading={priorityReading} />,
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
              final && held
                ? {
                    filename: runFilename("inspector"),
                    data: () => packInspectorResult(result, held),
                  }
                : undefined
            }
          />
        </>
      }
    >
        <TabsContent value="trace" className="m-0">
          <InspectorDocumentTrace
            key={rubricId}
            result={inspection}
            focus={traceFocus}
            onFocusConsumed={consumeTraceFocus}
          />
        </TabsContent>
        <TabsContent value="sections" className="m-0">
          <SectionsList key={rubricId} sections={sections} rubric={inspection.rubric} />
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
          {/* No side padding here: the conflict rows are the same full-width rows as the
              Sections tab and bring their own inset, so a padded wrapper put them 24px
              inside everything else on the card. The sentences above them take it instead. */}
          <div className="py-5 sm:py-6">
            <ConsistencyView
              findings={inspection.document_findings ?? []}
              status={inspection.consistency_status}
            />
          </div>
        </TabsContent>
    </ResultLayout>
    </DocumentSourceProvider>
  );
});

function SectionsList({
  sections,
  rubric,
}: {
  sections: SectionAssessment[];
  rubric: RubricSnapshot;
}) {
  const [query, setQuery] = useState("");
  const normalizedQuery = normalizeQuery(query);
  // Matched on the units, because a reader looking for "Efficacy" is looking for a unit
  // and does not know which section holds it.
  //
  // The units, and not only the section: a search used to keep a section whose units
  // matched and then show every unit in it, so finding one row returned twenty with
  // nothing marking the hit. The rule the other three follow is that a query filters the
  // leaf rows and a container left with nothing disappears.
  //
  // A section whose own name matches keeps all of its units, which is not an exception:
  // matching the name is a reader asking for that section, and the units are what it is.
  const visible = sections
    .map((section) =>
      !normalizedQuery
        || matchesQuery(normalizedQuery, section.section_name)
        ? section
        : {
            ...section,
            units: section.units.filter((unit) =>
              matchesQuery(normalizedQuery, unit.variable_name ?? section.section_name),
            ),
          },
    )
    .filter((section) => section.units.length > 0);

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
      <div className="px-5 py-5 sm:px-6">
        <ResultCardStack>
          {visible.map((section) => (
            <SectionCard key={section.section_name} section={section} rubric={rubric} />
          ))}
          {visible.length === 0 && (
            <EmptyState message="No section or unit matches that search" />
          )}
        </ResultCardStack>
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
function rubricLabel(rubric: RubricSnapshot): string {
  return rubric.revision ? `${rubric.display_name} · v${rubric.revision}` : rubric.display_name;
}

function AssessmentRow({
  item,
  title,
  requirement,
  rubric,
  showVerdict = title !== null,
  hideStatement = false,
}: {
  item: Assessment;
  /** What this is about. The section's name where a unit declares no variable. */
  title: string | null;
  requirement?: RequirementSnapshot;
  rubric?: RubricSnapshot;
  /** Single-unit cards already show this in their header; standalone findings do not. */
  showVerdict?: boolean;
  /**
   * For an absent section's units, whose statements assembly writes rather than a model:
   * "The Introduction section is not present in the document. It should cover: …" beside
   * a "Not present" pill, a "Section not found" line and the rubric requirement said one
   * fact three times - and under the authorship star, over words no model wrote.
   */
  hideStatement?: boolean;
}) {
  return (
    <div className="px-5 py-3.5 sm:px-6">
      {(title !== null || showVerdict) && <div className="flex flex-wrap items-baseline gap-x-4 gap-y-2">
        {title !== null && <p className={cn("min-w-0 flex-1 basis-48", ROW_TITLE)}>{title}</p>}
        {/* Right-aligned beside a title; with no title it leads the row, where the sentence
            under it starts, rather than floating alone at the far end of an empty line. */}
        {showVerdict && <div className={cn("flex shrink-0 items-center gap-2", title !== null && "ml-auto")}>
          {/* Muted text, not a second pill. `Optional` is the rubric author's decision
              about this unit, not a verdict about the document, and two pills on one row
              read as two judgements. */}
          {item.optional && (
            <span className="text-[11px] text-muted-foreground">Optional</span>
          )}
          <StatusPill status={item.verdict} />
        </div>}
      </div>}
      {/* The verdict is on the pill and nowhere else. It used to be repeated here as
          well, which made sense when a unit held several findings and each carried its
          own reason; with one verdict per unit the second copy says nothing. */}
      {!hideStatement && item.statement && (
        <Reading size="prominent" className="mt-1">
          {item.statement}
        </Reading>
      )}
      {requirement && rubric && <InspectorRequirement requirement={requirement} rubric={rubric} />}
      {item.cited_block_ids.length > 0 && (
        <div className={cn("mt-1.5", TRIGGER_AT_LINE_START)}>
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

function SectionCard({ section, rubric }: { section: SectionAssessment; rubric: RubricSnapshot }) {
  return (
    <CollapsibleCard
      title={section.section_name}
      trailing={section.units.length === 1 && section.units[0].variable_name === null
        ? <div className="flex items-center gap-2">
            {section.units[0].optional && <span className="text-xs text-muted-foreground">Optional</span>}
            <SignalChip tone={VERDICT_TONE[section.units[0].verdict]}>
              {VERDICT_LABEL[section.units[0].verdict]}
            </SignalChip>
          </div>
        : <ShortfallCounts section={section} />}
      defaultOpen={false}
      flush
    >
      {/* Dividers, not a second bordered box. The card already draws the boundary; a
          rounded border inside a rounded border was the third nesting level on a page
          Scout renders with two. */}
      <div className="divide-y divide-border/60">
        {/* An absent section says so once, here; what it should have covered is the
            rubric requirement under each unit. */}
        {section.is_present === false && (
          <p className="px-5 py-3.5 text-xs text-muted-foreground sm:px-6">
            Section not found in the document
          </p>
        )}
        {section.units.map((unit) => (
          <AssessmentRow
            key={unit.variable_name ?? section.section_name}
            item={unit}
            title={section.units.length === 1 && unit.variable_name === null ? null : unit.variable_name ?? section.section_name}
            requirement={rubric.requirements.find(requirement => requirement.id === unit.id)}
            rubric={rubric}
            hideStatement={section.is_present === false}
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
      // A conflict belongs to no unit, so it is not in the sum above.
      facts={
        conflicts > 0
          ? [
              {
                value: conflicts,
                label: `cross-section ${conflicts === 1 ? "conflict" : "conflicts"}`,
              },
            ]
          : []
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
    // Section summaries use dots, whether they carry one signal or several counts.
    return <SignalChip tone={VERDICT_TONE.specified}>{VERDICT_LABEL.specified}</SignalChip>;
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
      <div className="px-5 sm:px-6">
      <EmptyState
        tone={complete ? "clear" : "unknown"}
        message={
          complete
            ? "No cross-section conflicts identified"
            : "Consistency coverage is incomplete"
        }
        detail={consistencyDescription(status)}
      />
      </div>
    );
  }
  return (
    <div>
      {/* The count and the name are in the toolbar above; what is left is the one thing a
          reader cannot see - how much of the document the pass covered - and only when it
          was less than all of it. A complete pass is what a reader assumes. */}
      {status !== "complete" && (
        <InterfaceNote className="mx-5 mb-3 sm:mx-6">
          {consistencyDescription(status)}
        </InterfaceNote>
      )}
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
            showVerdict
          />
        ))}
      </div>
    </div>
  );
}

/** Do not invent a topic heading when the saved finding supplies none. */
function conflictTitle(finding: Assessment): string | null {
  return finding.variable_name ?? finding.section_name ?? null;
}

function consistencyDescription(
  status: InspectionResult["consistency_status"],
): string {
  if (status === "complete")
    return "The complete retained document context was checked across mapped sections.";
  if (status === "partial")
    return "The document exceeded the full-pass context bound; findings reflect the retained section-balanced context.";
  if (status === "failed")
    return "The consistency pass did not complete; every section assessment above is unaffected. To retry this check, run the analysis again. If it keeps failing, report it through Feedback with the downloaded JSON.";
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
