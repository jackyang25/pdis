"use client";

import { useEffect, useMemo, useRef, useState } from "react";
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
import { LabeledItem } from "@/components/labeled-item";
import { PageHeader } from "@/components/page-header";
import { RunPanel } from "@/components/run-panel";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  DIMENSION_NAMES,
  GRADE_LABELS,
  runInspector,
  type CrossSectionFinding,
  type DimensionName,
  type Dimensions,
  type Grade,
  type Header,
  type InspectorResponse,
  type SectionGrade,
  type VariableGrade,
} from "@/lib/api";
import {
  inspectorResultFilename,
  isInspectorResultFinal,
  packInspectorResult,
  unpackInspectorResult,
} from "@/lib/result-file";
import { useInspectorSession } from "@/lib/session";
import { cn } from "@/lib/utils";

const INSPECTOR_STEPS = [
  { key: "parse", label: "Parsing document" },
  { key: "label", label: "Mapping rubric sections" },
  { key: "grade", label: "Assessing rubric variables" },
  { key: "consistency", label: "Checking cross-section consistency" },
];

export default function InspectorPage() {
  return (
    <>
      <PageHeader
        title="Inspector"
        description="Check completeness, adherence, rigor, and cross-section consistency against the selected rubric."
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
      setResult(response);
    } catch (runError) {
      setError((runError as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function handleImport(file: File) {
    setError(null);
    try {
      const parsed = unpackInspectorResult(JSON.parse(await file.text()));
      if (!parsed?.inspection || !Array.isArray(parsed.inspection.section_grades)) {
        throw new Error("not an Inspector result file");
      }
      setStage(null);
      setProgress(null);
      setResult(parsed);
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
  const inspection = result.inspection;
  const final = isInspectorResultFinal(result);
  const variableCount = inspection.section_grades.reduce(
    (total, section) => total + section.variable_grades.length,
    0,
  );
  const consistencySummary = inspection.cross_section_findings.length > 0
    ? `${inspection.cross_section_findings.length} cross-section conflicts`
    : inspection.consistency_status === "complete"
      ? "consistency checked"
      : inspection.consistency_status === "not_applicable"
        ? "consistency not applicable"
        : inspection.consistency_status === "partial"
          ? "bounded consistency check"
          : "consistency incomplete";
  const subtitle = [
    `${inspection.section_grades.length} rubric sections`,
    variableCount > 0 ? `${variableCount} variables` : null,
    consistencySummary,
  ].filter(Boolean).join(" · ");

  return (
    <CollapsibleCard
      title={inspection.doc_id || "Inspection result"}
      subtitle={subtitle}
      defaultOpen
      contentClassName="px-0 py-0 sm:px-0"
      trailing={
        <FinalResultActions
          onNewAnalysis={onNewAnalysis}
          download={final ? {
              filename: inspectorResultFilename(result),
              data: packInspectorResult(result),
            } : undefined}
        />
      }
    >
      {!final && (
        <div className="border-b border-border bg-amber-500/[0.05] px-5 py-3 text-sm text-amber-800 dark:text-amber-300 sm:px-6">
          Inspector grading is incomplete. Complete the analysis before downloading a final result.
        </div>
      )}
      <DocumentSourceProvider blocks={inspection.blocks}>
        <Tabs defaultValue="overview" className="w-full">
          <div className="border-b border-border px-5 pt-2 sm:px-6">
            <TabsList className="w-full justify-start">
              <TabsTrigger value="overview">Overview</TabsTrigger>
              <TabsTrigger value="sections">Sections</TabsTrigger>
              <TabsTrigger value="consistency">Consistency</TabsTrigger>
            </TabsList>
          </div>
          <TabsContent value="overview" className="m-0 px-5 py-5 sm:px-6 sm:py-6">
            <Overview inspection={inspection} />
          </TabsContent>
          <TabsContent value="sections" className="m-0 px-5 py-5 sm:px-6 sm:py-6">
            <SectionsList sections={inspection.section_grades} />
          </TabsContent>
          <TabsContent value="consistency" className="m-0 px-5 py-5 sm:px-6 sm:py-6">
            <ConsistencyView
              findings={inspection.cross_section_findings}
              status={inspection.consistency_status}
            />
          </TabsContent>
        </Tabs>
      </DocumentSourceProvider>
    </CollapsibleCard>
  );
}

function Overview({ inspection }: { inspection: InspectorResponse["inspection"] }) {
  return (
    <div className="space-y-6">
      <section>
        <SectionHeading
          title="Overall assessment"
          description="Independent document-level rollups across the authored rubric."
        />
        <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-3">
          {DIMENSION_NAMES.map((dimension) => (
            <DimensionTile
              key={dimension}
              name={dimension}
              grade={inspection.dimensions[dimension].grade}
            />
          ))}
        </div>
      </section>

      <section>
        <SectionHeading
          title="Rubric map"
          description="Each row is one required section; color is only a reading aid for its letter grade."
        />
        <GradeMatrix sections={inspection.section_grades} />
      </section>

      <section>
        <SectionHeading
          title="Priority document issues"
          description="The most consequential rubric gaps, ordered deterministically from the section assessments."
        />
        {inspection.top_issues.length > 0 ? (
          <ol className="mt-3 divide-y divide-border rounded-lg border border-border">
            {inspection.top_issues.map((issue, index) => (
              <li key={`${issue}-${index}`} className="flex gap-3 px-4 py-3 text-sm leading-6">
                <span className="font-mono text-xs text-muted-foreground">{String(index + 1).padStart(2, "0")}</span>
                <span>{issue}</span>
              </li>
            ))}
          </ol>
        ) : (
          <EmptyState text="No priority issues were identified." />
        )}
      </section>
    </div>
  );
}

function SectionHeading({ title, description }: { title: string; description: string }) {
  return (
    <div>
      <h3 className="text-sm font-semibold tracking-tight">{title}</h3>
      <p className="mt-1 text-xs leading-5 text-muted-foreground">{description}</p>
    </div>
  );
}

function DimensionTile({ name, grade }: { name: DimensionName; grade: Grade }) {
  return (
    <div className="rounded-lg border border-border bg-muted/20 p-4">
      <div className="text-[11px] font-medium uppercase tracking-[0.08em] text-muted-foreground">
        {name}
      </div>
      <div className="mt-2 flex items-baseline gap-3">
        <span className={cn("font-mono text-3xl font-semibold tabular-nums", GRADE_TEXT[grade])}>
          {grade}
        </span>
        <span className="text-xs leading-5 text-muted-foreground">{GRADE_LABELS[grade]}</span>
      </div>
    </div>
  );
}

function GradeMatrix({ sections }: { sections: SectionGrade[] }) {
  return (
    <div className="mt-3 overflow-x-auto rounded-lg border border-border">
      <div className="grid min-w-[38rem] grid-cols-[minmax(11rem,1fr)_repeat(3,minmax(6rem,0.32fr))] border-b border-border bg-muted/30 px-4 py-2 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
        <span>Section</span>
        {DIMENSION_NAMES.map((dimension) => (
          <span key={dimension} className="text-center capitalize">{dimension}</span>
        ))}
      </div>
      <div className="divide-y divide-border">
        {sections.map((section) => (
          <div
            key={section.section_name}
            className="grid min-w-[38rem] grid-cols-[minmax(11rem,1fr)_repeat(3,minmax(6rem,0.32fr))] items-center px-4 py-2.5"
          >
            <div className="min-w-0 pr-4">
              <p className="truncate text-sm font-medium">{section.section_name}</p>
              {!section.is_present && <p className="text-xs text-muted-foreground">Not present</p>}
            </div>
            {DIMENSION_NAMES.map((dimension) => {
              const grade = section.dimensions[dimension].grade;
              return (
                <div key={dimension} className="flex justify-center">
                  <span
                    title={GRADE_LABELS[grade]}
                    className={cn(
                      "inline-flex h-7 min-w-10 items-center justify-center rounded-md px-2 font-mono text-xs font-semibold",
                      GRADE_SURFACE[grade],
                    )}
                  >
                    {grade}
                  </span>
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}

function SectionsList({ sections }: { sections: SectionGrade[] }) {
  return (
    <div className="space-y-3">
      <SectionHeading
        title="Section assessments"
        description="Open a section to inspect variable-level issues, recommendations, and exact document lineage."
      />
      {sections.map((section) => (
        <SectionCard key={section.section_name} section={section} />
      ))}
    </div>
  );
}

function SectionCard({
  section,
}: {
  section: SectionGrade;
}) {
  return (
    <CollapsibleCard
      title={section.section_name}
      subtitle={section.is_present ? undefined : "Required section not found"}
      trailing={<DimensionStrip dimensions={section.dimensions} />}
      defaultOpen={false}
    >
      {section.missing_variables.length > 0 && (
        <div className="mb-4 rounded-md border border-border bg-muted/20 px-3 py-2.5">
          <p className="text-xs text-muted-foreground">Required variables not stated</p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {section.missing_variables.map((variable) => (
              <Badge key={variable} variant="outline">{variable}</Badge>
            ))}
          </div>
        </div>
      )}
      {section.variable_grades.length === 0 ? (
        <DimensionDetails dimensions={section.dimensions} />
      ) : (
        <div className="divide-y divide-border overflow-hidden rounded-lg border border-border">
          {section.variable_grades.map((variable) => (
            <VariableRow key={variable.variable_name} variable={variable} />
          ))}
        </div>
      )}
    </CollapsibleCard>
  );
}

function VariableRow({
  variable,
}: {
  variable: VariableGrade;
}) {
  return (
    <div className="px-4 py-4">
      <div className="flex flex-col justify-between gap-2 sm:flex-row sm:items-center">
        <p className="text-sm font-medium">{variable.variable_name}</p>
        <DimensionStrip dimensions={variable.dimensions} compact />
      </div>
      <DimensionDetails dimensions={variable.dimensions} />
      {variable.block_ids.length > 0 && (
        <div className="mt-3">
          <DocumentSourceTrace blockIds={variable.block_ids} />
        </div>
      )}
    </div>
  );
}

function ConsistencyView({
  findings,
  status,
}: {
  findings: CrossSectionFinding[];
  status: InspectorResponse["inspection"]["consistency_status"];
}) {
  if (findings.length === 0) {
    const complete = status === "complete" || status === "not_applicable";
    return (
      <div className="rounded-lg border border-border bg-muted/15 px-5 py-5">
        <div className="flex items-start gap-3">
          {complete ? (
            <CheckCircle2 className="mt-0.5 h-4 w-4 text-emerald-600" />
          ) : (
            <AlertTriangle className="mt-0.5 h-4 w-4 text-amber-600" />
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
      {findings.map((finding, index) => (
        <article key={`${finding.description}-${index}`} className="rounded-lg border border-border p-4">
          <p className="text-sm leading-6">{finding.description}</p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {finding.sections.map((section) => (
              <Badge key={section} variant="outline">{section}</Badge>
            ))}
          </div>
          {finding.recommendation && (
            <div className="mt-3">
              <LabeledItem kind="recommendation">{finding.recommendation}</LabeledItem>
            </div>
          )}
          <div className="mt-3">
            <DocumentSourceTrace blockIds={finding.block_ids} />
          </div>
        </article>
      ))}
    </div>
  );
}

function consistencyDescription(status: InspectorResponse["inspection"]["consistency_status"]): string {
  if (status === "complete") return "The complete retained document context was checked across mapped sections.";
  if (status === "partial") return "The document exceeded the full-pass context bound; findings reflect the retained section-balanced context.";
  if (status === "failed") return "The consistency pass did not complete; section and variable grades remain valid.";
  if (status === "not_applicable") return "Fewer than two mapped sections were available for a cross-section comparison.";
  return "This saved result does not record consistency-pass completion.";
}

function DimensionStrip({ dimensions, compact = false }: { dimensions: Dimensions; compact?: boolean }) {
  return (
    <div className={cn("flex flex-wrap items-center gap-2", compact ? "text-xs" : "text-sm")}>
      {DIMENSION_NAMES.map((dimension) => {
        const grade = dimensions[dimension].grade;
        return (
          <span
            key={dimension}
            title={`${dimension}: ${GRADE_LABELS[grade]}`}
            className="inline-flex items-center gap-1.5 rounded-md bg-muted/40 px-2 py-1"
          >
            <span className="text-[10px] capitalize text-muted-foreground">{dimension}</span>
            <span className={cn("font-mono text-xs font-semibold", GRADE_TEXT[grade])}>{grade}</span>
          </span>
        );
      })}
    </div>
  );
}

function DimensionDetails({ dimensions }: { dimensions: Dimensions }) {
  const dimensionsWithContent = DIMENSION_NAMES.filter(
    (dimension) => dimensions[dimension].issues.length > 0 || dimensions[dimension].recommendation,
  );
  if (dimensionsWithContent.length === 0) return null;
  return (
    <Tabs defaultValue={dimensionsWithContent[0]} className="mt-4">
      <TabsList>
        {DIMENSION_NAMES.map((dimension) => (
          <TabsTrigger key={dimension} value={dimension} className="capitalize">
            {dimension}
          </TabsTrigger>
        ))}
      </TabsList>
      {DIMENSION_NAMES.map((dimension) => {
        const item = dimensions[dimension];
        return (
          <TabsContent key={dimension} value={dimension}>
            {item.issues.length === 0 && !item.recommendation ? (
              <p className="text-xs text-muted-foreground">No issues on this dimension.</p>
            ) : (
              <div className="space-y-2.5">
                {item.issues.map((issue, index) => (
                  <LabeledItem key={`${dimension}-${index}`} kind="issue">{issue}</LabeledItem>
                ))}
                {item.recommendation && (
                  <LabeledItem kind="recommendation">{item.recommendation}</LabeledItem>
                )}
              </div>
            )}
          </TabsContent>
        );
      })}
    </Tabs>
  );
}

function EmptyState({ text }: { text: string }) {
  return (
    <div className="mt-3 rounded-lg border border-dashed border-border px-4 py-6 text-center text-sm text-muted-foreground">
      {text}
    </div>
  );
}

const GRADE_TEXT: Record<Grade, string> = {
  A: "text-emerald-700 dark:text-emerald-300",
  B: "text-emerald-700 dark:text-emerald-300",
  C: "text-amber-700 dark:text-amber-300",
  D: "text-orange-700 dark:text-orange-300",
  F: "text-[hsl(var(--tone-danger))]",
  "N/A": "text-muted-foreground",
};

const GRADE_SURFACE: Record<Grade, string> = {
  A: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  B: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  C: "bg-amber-500/10 text-amber-700 dark:text-amber-300",
  D: "bg-orange-500/10 text-orange-700 dark:text-orange-300",
  F: "bg-[hsl(var(--tone-danger))]/10 text-[hsl(var(--tone-danger))]",
  "N/A": "bg-muted text-muted-foreground",
};
