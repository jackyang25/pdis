"use client";

import { useRef } from "react";
import { PageHeader } from "@/components/page-header";
import { RunPanel } from "@/components/run-panel";
import { ConfigurationFields } from "@/components/configuration-fields";
import { HeaderGuard } from "@/components/header-guard";
import { Badge } from "@/components/ui/badge";
import { DownloadButton } from "@/components/download-button";
import { LabeledItem } from "@/components/labeled-item";
import { CollapsibleCard } from "@/components/collapsible-card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  runInspector,
  DIMENSION_NAMES,
  GRADE_LABELS,
  type CrossSectionFinding,
  type DimensionName,
  type Dimensions,
  type Header,
  type InspectorResponse,
  type SectionGrade,
  type VariableGrade,
} from "@/lib/api";
import { Ask } from "@/components/assistant/ask";
import { useInspectorSession } from "@/lib/session";
import { packInspectorResult, unpackInspectorResult } from "@/lib/result-file";

const INSPECTOR_STEPS = [
  { key: "parse", label: "Parsing document" },
  { key: "label", label: "Labeling sections" },
  { key: "grade", label: "Grading sections" },
  { key: "consistency", label: "Checking consistency" },
];

export default function InspectorPage() {
  return (
    <>
      <PageHeader title="Inspector" description="Check completeness, adherence, rigor, and cross-section consistency against the selected rubric." />
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

  async function handleRun(file: File) {
    setBusy(true);
    setError(null);
    setStage(null);
    setProgress(null);
    try {
      const res = await runInspector(file, header, (s, p) => {
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

  // Re-open a previously downloaded inspection and
  // render it - no re-run, no backend call.
  async function handleImport(file: File) {
    setError(null);
    try {
      const parsed = unpackInspectorResult(JSON.parse(await file.text()));
      if (!parsed?.inspection || !Array.isArray(parsed.inspection.section_grades)) {
        throw new Error("not an Inspector result file");
      }
      setStage(null);
      setResult(parsed);
    } catch (err) {
      setError(`Could not import result: ${(err as Error).message}`);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <RunPanel
        configuration={<ConfigurationFields />}
        accept=".docx,.pdf,.pptx"
        busy={busy}
        onRun={handleRun}
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
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) handleImport(f);
                e.target.value = "";
              }}
            />
          </div>
        }
      />
      {error && <p className="text-sm text-destructive">{error}</p>}
      {result && (
        <>
          <OverallCard result={result} />
          <CrossSectionCard findings={result.inspection.cross_section_findings ?? []} />
          <SectionsList sections={result.inspection.section_grades} />
        </>
      )}
      {result && <Ask resultType="inspector" result={result.inspection} />}
    </div>
  );
}

function OverallCard({ result }: { result: InspectorResponse }) {
  const dims = result.inspection.dimensions;
  return (
    <div className="rounded-lg border border-border bg-card px-5 py-5">
      <div className="flex flex-col items-start justify-between gap-3 sm:flex-row">
        <div>
          <div className="text-xs uppercase tracking-wide text-muted-foreground">
            Overall grades
          </div>
          <div className="mt-1 font-mono text-sm">{result.inspection.doc_id}</div>
        </div>
        <DownloadButton
          filename={`${result.inspection.doc_id}_inspection.json`}
          data={packInspectorResult(result)}
          format="json"
          label="Download JSON"
        />
      </div>
      <div className="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-3">
        {DIMENSION_NAMES.map((d) => (
          <DimensionTile key={d} name={d} grade={dims[d].grade} />
        ))}
      </div>
    </div>
  );
}

function DimensionTile({ name, grade }: { name: DimensionName; grade: string }) {
  return (
    <div className="rounded-md border border-border bg-muted/30 px-4 py-3">
      <div className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
        {name}
      </div>
      <div className="mt-1 flex items-baseline gap-2">
        <span className="font-mono text-2xl font-semibold tabular-nums">{grade}</span>
        <span className="text-xs text-muted-foreground">{GRADE_LABELS[grade] ?? ""}</span>
      </div>
    </div>
  );
}

function CrossSectionCard({ findings }: { findings: CrossSectionFinding[] }) {
  if (findings.length === 0) return null;
  return (
    <div className="rounded-lg border border-amber-500/30 bg-amber-500/[0.04] px-5 py-5">
      <div className="flex flex-wrap items-baseline gap-2">
        <span className="text-xs font-medium uppercase tracking-wide text-amber-700 dark:text-amber-400">
          Cross-section consistency
        </span>
        <span className="text-xs text-muted-foreground">
          {findings.length} conflict{findings.length === 1 ? "" : "s"} spanning multiple sections
        </span>
      </div>
      <ul className="mt-3 flex flex-col gap-3">
        {findings.map((f, idx) => (
          <li key={idx} className="rounded-md border border-border bg-card px-4 py-3">
            <p className="text-sm leading-relaxed text-foreground">{f.description}</p>
            {f.sections.length > 0 && (
              <div className="mt-2 flex flex-wrap items-center gap-1.5">
                {f.sections.map((s) => (
                  <Badge key={s} variant="outline">
                    {s}
                  </Badge>
                ))}
              </div>
            )}
            {f.recommendation && (
              <p className="mt-2 border-l-2 border-amber-500/50 pl-3 text-xs leading-relaxed text-muted-foreground">
                {f.recommendation}
              </p>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

function SectionsList({ sections }: { sections: SectionGrade[] }) {
  return (
    <div className="flex flex-col gap-3">
      {sections.map((section) => (
        <SectionCard key={section.section_name} section={section} />
      ))}
    </div>
  );
}

function SectionCard({ section }: { section: SectionGrade }) {
  return (
    <CollapsibleCard
      title={section.section_name}
      subtitle={section.is_present ? undefined : "Missing"}
      trailing={<DimensionStrip dimensions={section.dimensions} />}
      defaultOpen={false}
    >
      {section.missing_variables.length > 0 && (
        <div className="mb-4 flex flex-wrap items-center gap-1.5">
          <span className="text-xs text-muted-foreground">Missing variables:</span>
          {section.missing_variables.map((v) => (
            <Badge key={v} variant="outline">
              {v}
            </Badge>
          ))}
        </div>
      )}

      {/* Prose sections show their own dimension issues here.
          Variable-bearing sections delegate detail to variables below. */}
      {section.variable_grades.length === 0 && (
        <DimensionDetails dimensions={section.dimensions} />
      )}

      {section.variable_grades.length > 0 && (
        <ul className="flex flex-col gap-3">
          {section.variable_grades.map((v) => (
            <VariableRow key={v.variable_name} variable={v} />
          ))}
        </ul>
      )}
    </CollapsibleCard>
  );
}

function VariableRow({ variable }: { variable: VariableGrade }) {
  return (
    <li className="rounded-md bg-secondary/40 px-4 py-3">
      <div className="flex items-start justify-between gap-4">
        <div className="text-sm font-medium">{variable.variable_name}</div>
        <DimensionStrip dimensions={variable.dimensions} compact />
      </div>

      <DimensionDetails dimensions={variable.dimensions} />
    </li>
  );
}

const GRADE_COLOR: Record<string, string> = {
  A: "text-emerald-600 dark:text-emerald-400",
  B: "text-emerald-700 dark:text-emerald-300",
  C: "text-amber-600 dark:text-amber-400",
  D: "text-orange-600 dark:text-orange-400",
  F: "text-red-600 dark:text-red-400",
  "N/A": "text-muted-foreground",
};

function DimensionStrip({
  dimensions,
  compact = false,
}: {
  dimensions: Dimensions;
  compact?: boolean;
}) {
  return (
    <div
      className={`flex shrink-0 items-center gap-3 whitespace-nowrap ${
        compact ? "text-xs" : "text-sm"
      }`}
    >
      {DIMENSION_NAMES.map((d, idx) => {
        const g = dimensions[d].grade;
        return (
          <span key={d} className="flex items-center gap-1.5" title={GRADE_LABELS[g] ?? g}>
            {idx > 0 && <span className="text-muted-foreground">·</span>}
            <span className="text-[10px] uppercase tracking-wide text-muted-foreground">
              {d}
            </span>
            <span className={`font-mono font-semibold tabular-nums ${GRADE_COLOR[g] ?? ""}`}>
              {g}
            </span>
          </span>
        );
      })}
    </div>
  );
}

function DimensionDetails({ dimensions }: { dimensions: Dimensions }) {
  const anyContent =
    DIMENSION_NAMES.some(
      (d) => dimensions[d].issues.length > 0 || dimensions[d].recommendation,
    );
  if (!anyContent) return null;

  return (
    <div className="mt-4">
      <Tabs defaultValue={DIMENSION_NAMES[0]}>
        <TabsList>
          {DIMENSION_NAMES.map((d) => {
            const dg = dimensions[d];
            const count = dg.issues.length + (dg.recommendation ? 1 : 0);
            return (
              <TabsTrigger key={d} value={d}>
                <span className="capitalize">{d}</span>
                {count > 0 && (
                  <span className="ml-1.5 text-[10px] text-muted-foreground">{count}</span>
                )}
              </TabsTrigger>
            );
          })}
        </TabsList>
        {DIMENSION_NAMES.map((d) => {
          const dg = dimensions[d];
          const empty = dg.issues.length === 0 && !dg.recommendation;
          return (
            <TabsContent key={d} value={d}>
              {empty ? (
                <p className="text-xs text-muted-foreground">No items on this dimension.</p>
              ) : (
                <div className="flex flex-col gap-3">
                  {dg.issues.map((issue, idx) => (
                    <LabeledItem key={`${d}-i-${idx}`} kind="issue">
                      {issue}
                    </LabeledItem>
                  ))}
                  {dg.recommendation && (
                    <LabeledItem kind="recommendation">{dg.recommendation}</LabeledItem>
                  )}
                </div>
              )}
            </TabsContent>
          );
        })}
      </Tabs>
    </div>
  );
}
