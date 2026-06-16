"use client";

import { PageHeader } from "@/components/page-header";
import { RunPanel } from "@/components/run-panel";
import { HeaderGuard } from "@/components/header-guard";
import { EmptyState } from "@/components/empty-state";
import { Badge } from "@/components/ui/badge";
import { DownloadButton } from "@/components/download-button";
import { LabeledItem } from "@/components/labeled-item";
import { CollapsibleCard } from "@/components/collapsible-card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  runReviewer,
  DIMENSION_NAMES,
  GRADE_LABELS,
  type DimensionName,
  type Dimensions,
  type Header,
  type ReviewerResponse,
  type SectionGrade,
  type VariableGrade,
} from "@/lib/api";
import { useReviewerSession } from "@/lib/session";

const PD_REVIEWER_STEPS = [
  { key: "parse", label: "Parsing document" },
  { key: "label", label: "Labeling sections" },
  { key: "grade", label: "Grading sections" },
];

export default function ReviewerPage() {
  return (
    <>
      <PageHeader
        title="Reviewer"
        description="Grade a document against a TPP rubric."
      />
      <HeaderGuard>{(header) => <ReviewerView header={header as Header} />}</HeaderGuard>
    </>
  );
}

function ReviewerView({ header }: { header: Header }) {
  const { result, busy, stage, error, setResult, setBusy, setStage, setError } =
    useReviewerSession();

  async function handleRun(file: File) {
    setBusy(true);
    setError(null);
    setStage(null);
    try {
      const res = await runReviewer(file, header, setStage);
      setResult(res);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <RunPanel
        accept=".docx,.pdf"
        busy={busy}
        onRun={handleRun}
        steps={PD_REVIEWER_STEPS}
        currentStage={stage}
      />
      {error && <p className="text-sm text-destructive">{error}</p>}
      {result && (
        <>
          <OverallCard result={result} />
          <SectionsList sections={result.review.section_grades} />
        </>
      )}
      {!result && !busy && !error && (
        <EmptyState message="Upload a .docx to begin." />
      )}
    </div>
  );
}

function OverallCard({ result }: { result: ReviewerResponse }) {
  const dims = result.review.dimensions;
  return (
    <div className="rounded-lg border border-border bg-card px-6 py-5">
      <div className="flex items-start justify-between">
        <div>
          <div className="text-xs uppercase tracking-wide text-muted-foreground">
            Overall grades
          </div>
          <div className="mt-1 font-mono text-sm">{result.review.doc_id}</div>
        </div>
        <DownloadButton
          filename={`${result.review.doc_id}_review.json`}
          data={result}
          format="json"
          label="Download JSON"
        />
      </div>
      <div className="mt-5 grid grid-cols-3 gap-3">
        {DIMENSION_NAMES.map((d) => (
          <DimensionTile key={d} name={d} grade={dims[d].grade} />
        ))}
      </div>
    </div>
  );
}

function DimensionTile({ name, grade }: { name: DimensionName; grade: string }) {
  return (
    <div className="rounded-md border border-border bg-secondary/30 px-4 py-3">
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
