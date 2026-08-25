"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, CheckCircle2 } from "lucide-react";
import { CollapsibleCard } from "@/components/collapsible-card";
import { ErrorMessage } from "@/components/ui/error-message";
import { ConfigurationFields } from "@/components/configuration-fields";
import {
  DocumentSourceProvider,
  DocumentSourceTrace,
} from "@/components/document-source-trace";
import { FinalResultActions } from "@/components/final-result-actions";
import { HeaderGuard } from "@/components/header-guard";
import {
  InspectorSignalHelp,
  InspectorSignalLabel,
} from "@/components/inspector-signal-help";
import { InspectorDocumentTrace } from "@/components/inspector-document-trace";
import { PriorityPanel } from "@/components/ui/priority-panel";
import { SectionHeading } from "@/components/ui/section-heading";
import { LabeledItem } from "@/components/labeled-item";
import { PageHeader } from "@/components/page-header";
import { RunPanel } from "@/components/run-panel";
import { RunHistory } from "@/components/run-history";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  LEVEL_LABELS,
  REASON_LABELS,
  SHORTFALL_LEVELS,
  STATUS_DESCRIPTION,
  STATUS_LABEL,
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
import { TONE_TEXT, TONE_TINT } from "@/lib/tone";
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
        {(header, ready) => <InspectorView header={header as Header} ready={ready} />}
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
      const response = await runInspector(file, header, (nextStage, nextProgress) => {
        setStage(nextStage);
        setProgress(nextProgress ?? null);
      });
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
  const { results, selectedId, selectResult, removeResult } = useInspectorSession();
  const inspection = result.inspection;
  const final = isInspectorResultFinal(result);
  const [resultTab, setResultTab] = useState("trace");
  const [traceFocusBlockId, setTraceFocusBlockId] = useState<string | null>(null);
  const openBlockInTrace = useCallback((blockId: string) => {
    setTraceFocusBlockId(blockId);
    setResultTab("trace");
  }, []);
  const consumeTraceFocus = useCallback((blockId: string) => {
    setTraceFocusBlockId((current) => (current === blockId ? null : current));
  }, []);

  const findings = worklist(inspection);
  const sections = inspection.sections ?? [];
  const unitCount = sections.reduce((total, section) => total + section.units.length, 0);
  const conflicts = inspection.document_findings?.length ?? 0;
  const subtitle = [
    `${sections.length} rubric sections`,
    `${unitCount} units`,
    `${findings.length} finding${findings.length === 1 ? "" : "s"}`,
    conflicts > 0 ? `${conflicts} cross-section conflict${conflicts === 1 ? "" : "s"}` : null,
  ].filter(Boolean).join(" · ");

  return (
    <CollapsibleCard
      title={inspection.doc_id || "Inspection result"}
      subtitle={subtitle}
      defaultOpen
      contentClassName="px-0 py-0 sm:px-0"
      trailing={
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
          download={final ? {
              filename: inspectorResultFilename(result),
              data: packInspectorResult(result),
            } : undefined}
        />
        </>
      }
    >
      {!final && (
        <div className={cn("border-b border-border bg-[hsl(var(--tone-warning))]/[0.06] px-5 py-3 text-sm sm:px-6", TONE_TEXT.warning)}>
          This assessment is incomplete. Complete the analysis before downloading a final result.
        </div>
      )}
      <DocumentSourceProvider
        blocks={inspection.blocks}
        onOpenInTrace={openBlockInTrace}
      >
        <Tabs value={resultTab} onValueChange={setResultTab} className="w-full">
          <div className="flex items-center justify-between gap-3 border-b border-border px-5 pt-2 sm:px-6">
            <TabsList className="justify-start border-b-0">
              {/* The document is what Inspector is about, so it opens on the
                  document. Scout opens on its evidence for the same reason. */}
              <TabsTrigger value="trace">Documents</TabsTrigger>
              <TabsTrigger value="sections">Sections</TabsTrigger>
              <TabsTrigger value="consistency">Consistency</TabsTrigger>
            </TabsList>
            <InspectorSignalHelp />
          </div>
          <TabsContent value="trace" className="m-0">
            <InspectorDocumentTrace
              result={inspection}
              focusBlockId={traceFocusBlockId}
              onFocusBlockConsumed={consumeTraceFocus}
            />
          </TabsContent>
          <TabsContent value="sections" className="m-0 px-5 py-5 sm:px-6 sm:py-6">
            <SectionsList sections={sections} inspection={inspection} />
          </TabsContent>
          <TabsContent value="consistency" className="m-0 px-5 py-5 sm:px-6 sm:py-6">
            <ConsistencyView
              findings={inspection.document_findings ?? []}
              status={inspection.consistency_status}
            />
          </TabsContent>
        </Tabs>
      </DocumentSourceProvider>
    </CollapsibleCard>
  );
}

function SectionsList({
  sections,
  inspection,
}: {
  sections: SectionAssessment[];
  inspection: InspectionResult;
}) {
  const items = useMemo(() => selectInspectorPriorities(inspection), [inspection]);
  // Read here rather than passed down: the store is the session's, and threading a
  // digest through the view would make every intermediate component know about it.
  const selectedId = useInspectorSession((state) => state.selectedId);
  const digest = usePriorityDigest(
    selectedId
      ? {
          resultId: selectedId,
          // The tool's own catalog sentence, so nothing here restates its authority.
          authority: toolAuthority("inspector"),
          orderNote: INSPECTOR_ORDER_NOTE,
          items,
          analysis: splitResultContext(inspection).analysis,
          blockIds: (inspection.blocks ?? []).map((block) => block.id),
          org: inspection.org ?? "",
          interventionClass: inspection.intervention_class ?? "",
          indication: inspection.indication ?? "",
        }
      : null,
  );

  return (
    <div className="space-y-6">
      <PriorityPanel
        attribution="by Inspector"
        items={items}
        emptyMessage={INSPECTOR_EMPTY_MESSAGE}
        orderNote={INSPECTOR_ORDER_NOTE}
        digest={digest?.state === "ready" ? digest.digest.digest : undefined}
        nominations={digest?.state === "ready" ? digest.digest.nominations : []}
        digestLoading={digest?.state === "loading"}
        digestError={digest?.state === "failed" ? digest.reason : undefined}
      />
      <div className="space-y-3">
        <SectionHeading
          title="Section assessments"
          description="Each row carries its own counts. Open a section to see every unit the rubric asks about, its findings, and the passages behind them."
        />
        {sections.map((section) => (
          <SectionCard key={section.section_name} section={section} />
        ))}
      </div>
    </div>
  );
}

/**
 * One finding, rendered the same way wherever it appears.
 *
 * The section list and the findings list show the same object, so they share one
 * renderer; two would be two things to keep in step.
 */
function FindingBody({ finding, showUnit = true }: { finding: RubricFinding; showUnit?: boolean }) {
  return (
    <div className="min-w-0 flex-1">
      <p className="flex flex-wrap items-baseline gap-x-1.5">
        {showUnit && (
          <span className="font-medium">
            {finding.variable_name ?? finding.section_name ?? "Across sections"}
          </span>
        )}
        <InspectorSignalLabel topic="finding" className="text-xs text-muted-foreground">
          {REASON_LABELS[finding.reason]}
        </InspectorSignalLabel>
      </p>
      <p className="mt-0.5">{finding.statement}</p>
      {finding.recommendation && (
        <p className="mt-0.5 text-muted-foreground">{finding.recommendation}</p>
      )}
      {finding.cited_block_ids.length > 0 && (
        <div className="mt-1.5">
          <DocumentSourceTrace blockIds={finding.cited_block_ids} />
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
      <div className="divide-y divide-border overflow-hidden rounded-lg border border-border">
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
 * A section's units that fall short, by level.
 *
 * A zero says nothing, so it is not shown: on a six-section rubric most of these
 * were "0" and the eye had to sort twelve numbers to find the two that mattered.
 * The counts are of units, so they are bounded by the rubric rather than by how
 * much the model had to say.
 */
function ShortfallCounts({ section }: { section: SectionAssessment }) {
  const counts = sectionShortfalls(section);
  const shown = SHORTFALL_LEVELS.filter((level) => counts[level] > 0);
  if (shown.length === 0) {
    return <span className="text-xs text-muted-foreground">Met</span>;
  }
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs">
      {shown.map((level) => (
        <span
          key={level}
          className={cn(
            "inline-flex items-center gap-1.5 rounded-md px-2 py-1",
            LEVEL_SURFACE[level],
          )}
        >
          <span>{LEVEL_LABELS[level]}</span>
          <span className="font-semibold tabular-nums">{counts[level]}</span>
        </span>
      ))}
    </div>
  );
}

function UnitRow({ unit, sectionName }: { unit: UnitAssessment; sectionName: string }) {
  return (
    <div className="px-4 py-3">
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <p className="min-w-0 flex-1 truncate text-sm font-medium">
          {unit.variable_name ?? sectionName}
        </p>
        <div className="flex items-center gap-2">
          {unit.optional && <Badge variant="outline">Optional</Badge>}
          <StatusPill status={unit.status} />
        </div>
      </div>
      {unit.findings.length > 0 && (
        <ul className="mt-2.5 space-y-2.5 text-sm leading-6">
          {unit.findings.map((finding) => (
            <li key={finding.id}>
              {/* The unit's name is the row heading, so the finding does not
                  repeat it here. */}
              <FindingBody finding={finding} showUnit={false} />
            </li>
          ))}
        </ul>
      )}
    </div>
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
    return (
      <div className="rounded-lg border border-border bg-muted/15 px-5 py-5">
        <div className="flex items-start gap-3">
          {complete ? (
            <CheckCircle2 className={cn("mt-0.5 h-4 w-4", TONE_TEXT.success)} />
          ) : (
            <AlertTriangle className={cn("mt-0.5 h-4 w-4", TONE_TEXT.warning)} />
          )}
          <div>
            <p className="text-sm font-medium">
              {complete ? "No cross-section conflicts identified" : "Consistency coverage is incomplete"}
            </p>
            <p className="mt-1 text-xs leading-5 text-muted-foreground">
              {consistencyDescription(status)}
            </p>
          </div>
        </div>
      </div>
    );
  }
  return (
    <div className="space-y-3">
      <SectionHeading
        title={`${findings.length} cross-section conflict${findings.length === 1 ? "" : "s"}`}
        description={consistencyDescription(status)}
      />
      {findings.map((finding) => (
        <article key={finding.id} className="rounded-lg border border-border p-4">
          <p className="text-sm leading-6">{finding.statement}</p>
          {finding.recommendation && (
            <div className="mt-3">
              <LabeledItem kind="recommendation">{finding.recommendation}</LabeledItem>
            </div>
          )}
          <div className="mt-3">
            <DocumentSourceTrace blockIds={finding.cited_block_ids} />
          </div>
        </article>
      ))}
    </div>
  );
}

function consistencyDescription(status: InspectionResult["consistency_status"]): string {
  if (status === "complete") return "The complete retained document context was checked across mapped sections.";
  if (status === "partial") return "The document exceeded the full-pass context bound; findings reflect the retained section-balanced context.";
  if (status === "failed") return "The consistency pass did not complete; every section assessment above is unaffected.";
  if (status === "not_applicable") return "Fewer than two mapped sections were available for a cross-section comparison.";
  return "This saved result does not record consistency-pass completion.";
}

function StatusPill({ status }: { status: UnitStatus }) {
  return (
    <InspectorSignalLabel topic="status">
      <span
        title={STATUS_DESCRIPTION[status]}
        className={cn(
          "inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium",
          STATUS_SURFACE[status],
        )}
      >
        {STATUS_LABEL[status]}
      </span>
    </InspectorSignalLabel>
  );
}

/* The short forms moved to `lib/api.ts` as `STATUS_LABEL`. They lived here, so the document
   trace could not reach them and rendered the description as pill text instead. Colour is
   still a local concern: see `STATUS_SURFACE`. */

// Half of these reached the tone tokens and half wrote the palette out with a hand-kept
// dark-mode variant beside it, for verdicts that sit in the same row as each other.
const STATUS_SURFACE: Record<UnitStatus, string> = {
  met: TONE_TINT.success,
  could_be_stronger: TONE_TINT.warning,
  not_met: TONE_TINT.danger,
  not_applicable: TONE_TINT.neutral,
};

const LEVEL_SURFACE: Record<FindingLevel, string> = {
  not_met: TONE_TINT.danger,
  could_be_stronger: TONE_TINT.warning,
};
