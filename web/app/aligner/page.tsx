"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowRight, Check, CircleHelp, Loader2, Upload } from "lucide-react";
import { Ask } from "@/components/assistant/ask";
import { CollapsibleCard } from "@/components/collapsible-card";
import { FinalResultActions } from "@/components/final-result-actions";
import { PageHeader } from "@/components/page-header";
import { ProgressSteps } from "@/components/progress-steps";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  fetchDocumentTypes,
  fetchIndications,
  runAligner,
  type AlignmentLink,
  type AlignmentRelation,
  type AlignmentResult,
  type AlignmentUnit,
  type AlignmentUnitType,
  type ContentBlock,
  type DocumentType,
} from "@/lib/api";
import {
  alignerResultFilename,
  packAlignerResult,
  unpackAlignerResult,
} from "@/lib/result-file";
import { useAlignerSession } from "@/lib/session";
import { cn } from "@/lib/utils";
import { displayLabel } from "@/lib/display-label";

const STEPS = [
  { key: "parse", label: "Parsing documents" },
  { key: "extract", label: "Extracting traceable units" },
  { key: "align", label: "Aligning documents" },
];
const RELATIONS: AlignmentRelation[] = [
  "aligned",
  "modified",
  "conflict",
  "missing",
  "introduced",
];
const UNIT_TYPES: AlignmentUnitType[] = [
  "target",
  "activity",
  "milestone",
  "requirement",
  "dependency",
  "risk_response",
];
const RELATION_STYLES: Record<AlignmentRelation, string> = {
  aligned: "border-emerald-500/25 bg-emerald-500/[0.07] text-emerald-700",
  modified: "border-amber-500/30 bg-amber-500/[0.07] text-amber-700",
  conflict: "border-red-500/25 bg-red-500/[0.06] text-red-700",
  missing: "border-slate-400/30 bg-slate-500/[0.06] text-slate-700",
  introduced: "border-blue-500/25 bg-blue-500/[0.06] text-blue-700",
};

export default function AlignerPage() {
  const session = useAlignerSession();
  const [documentTypes, setDocumentTypes] = useState<DocumentType[] | null>(null);
  const [indications, setIndications] = useState<string[]>([]);
  const [org, setOrg] = useState("");
  const [intervention, setIntervention] = useState("");
  const [indication, setIndication] = useState("");
  const [referenceType, setReferenceType] = useState("");
  const [comparisonType, setComparisonType] = useState("");
  const [referenceFile, setReferenceFile] = useState<File | null>(null);
  const [comparisonFile, setComparisonFile] = useState<File | null>(null);
  const [showSetup, setShowSetup] = useState(!session.result);
  const importRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (session.result) setShowSetup(false);
  }, [session.result]);

  useEffect(() => {
    fetchDocumentTypes()
      .then(setDocumentTypes)
      .catch((error: Error) => session.setError(error.message));
  }, [session.setError]);

  useEffect(() => {
    if (!intervention) {
      setIndications([]);
      return;
    }
    fetchIndications(intervention).then(setIndications).catch(() => setIndications([]));
  }, [intervention]);

  const supported = useMemo(
    () => (documentTypes ?? []).filter((item) => item.supports.aligner),
    [documentTypes],
  );
  const orgs = unique(supported.map((item) => item.org));
  const interventions = unique(
    supported.filter((item) => item.org === org).map((item) => item.intervention_class),
  );
  const sourceTypes = supported.filter(
    (item) => item.org === org && item.intervention_class === intervention,
  );
  const ready = Boolean(
    org && intervention && indication && referenceType && comparisonType && referenceFile && comparisonFile,
  );

  async function handleRun() {
    if (!ready || !referenceFile || !comparisonFile) return;
    session.setBusy(true);
    session.setError(null);
    session.setStage(null);
    session.setProgress(null);
    try {
      const result = await runAligner(
        referenceFile,
        comparisonFile,
        {
          org,
          reference_source_type: referenceType,
          comparison_source_type: comparisonType,
          intervention_class: intervention,
          indication,
        },
        (stage, progress) => {
          session.setStage(stage);
          session.setProgress(progress ?? null);
        },
      );
      session.setResult(result);
    } catch (error) {
      session.setError((error as Error).message);
    } finally {
      session.setBusy(false);
    }
  }

  async function handleImport(file: File) {
    session.setError(null);
    try {
      session.setResult(unpackAlignerResult(JSON.parse(await file.text())));
    } catch (error) {
      session.setError(`Could not import result: ${(error as Error).message}`);
    }
  }

  return (
    <>
      <PageHeader
        title="Aligner"
        description="Trace what was preserved, changed, contradicted, omitted, or introduced across two development documents."
      />
      <div className="flex flex-col gap-6">
        {(!session.result || showSetup) && (
          <section className="rounded-lg border border-border bg-card p-5 sm:p-6">
            <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
              <ConfigField label="Organization">
                <ConfigSelect
                  value={org}
                  options={orgs.map((value) => ({ value, label: displayLabel(value) }))}
                  disabled={!documentTypes}
                  onChange={(value) => {
                    setOrg(value);
                    setIntervention("");
                    setIndication("");
                    setReferenceType("");
                    setComparisonType("");
                  }}
                />
              </ConfigField>
              <ConfigField label="Intervention">
                <ConfigSelect
                  value={intervention}
                  options={interventions.map((value) => ({ value, label: displayLabel(value) }))}
                  disabled={!org}
                  onChange={(value) => {
                    setIntervention(value);
                    setIndication("");
                    setReferenceType("");
                    setComparisonType("");
                  }}
                />
              </ConfigField>
              <ConfigField label="Reference type">
                <ConfigSelect
                  value={referenceType}
                  options={sourceTypes.map((item) => ({ value: item.source_type, label: displayLabel(item.source_type) }))}
                  disabled={!intervention}
                  onChange={setReferenceType}
                />
              </ConfigField>
              <ConfigField label="Comparison type">
                <ConfigSelect
                  value={comparisonType}
                  options={sourceTypes.map((item) => ({ value: item.source_type, label: displayLabel(item.source_type) }))}
                  disabled={!intervention}
                  onChange={setComparisonType}
                />
              </ConfigField>
            </div>

            <div className="mt-5 max-w-[calc(25%-0.75rem)] min-w-[15rem]">
              <ConfigField label="Indication">
                <ConfigSelect
                  value={indication}
                  options={indications.map((value) => ({ value, label: displayLabel(value) }))}
                  disabled={!intervention}
                  onChange={setIndication}
                />
              </ConfigField>
            </div>

            <div className="mt-6 grid gap-4 border-t border-border/80 pt-6 md:grid-cols-2">
              <FileSlot
                label="Reference document"
                helper="The baseline whose commitments should be carried forward."
                file={referenceFile}
                disabled={session.busy}
                onChange={setReferenceFile}
              />
              <FileSlot
                label="Comparison document"
                helper="The later or downstream artifact being checked."
                file={comparisonFile}
                disabled={session.busy}
                onChange={setComparisonFile}
              />
            </div>

            <div className="mt-5 flex flex-col-reverse gap-3 border-t border-border/80 pt-5 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-h-9">
                {session.busy ? (
                  <ProgressSteps
                    steps={STEPS}
                    busy
                    currentStage={session.stage}
                    progress={session.progress}
                  />
                ) : (
                  <div className="flex h-9 items-center gap-2 text-xs text-muted-foreground">
                    <span>Open a saved alignment:</span>
                    <button className="font-medium text-foreground hover:opacity-65" onClick={() => importRef.current?.click()}>
                      Import JSON
                    </button>
                    <input
                      ref={importRef}
                      type="file"
                      accept=".json,application/json"
                      className="hidden"
                      onChange={(event) => {
                        const file = event.target.files?.[0];
                        if (file) void handleImport(file);
                        event.target.value = "";
                      }}
                    />
                  </div>
                )}
              </div>
              <Button className="min-w-[8rem]" disabled={!ready || session.busy} onClick={handleRun}>
                {session.busy ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Aligning</> : "Run alignment"}
              </Button>
            </div>
          </section>
        )}

        {session.error && <p className="text-sm text-destructive">{session.error}</p>}
        {session.result && (
          <AlignmentView
            result={session.result.alignment}
            onNewAnalysis={() => setShowSetup(true)}
          />
        )}
        {session.result && <Ask resultType="aligner" result={session.result.alignment} />}
      </div>
    </>
  );
}

function AlignmentView({
  result,
  onNewAnalysis,
}: {
  result: AlignmentResult;
  onNewAnalysis: () => void;
}) {
  const [relationFilter, setRelationFilter] = useState<AlignmentRelation | "all">("all");
  const [unitTypeFilter, setUnitTypeFilter] = useState<AlignmentUnitType | "all">("all");
  const units = useMemo(() => new Map(result.units.map((unit) => [unit.id, unit])), [result.units]);
  const blocks = useMemo(() => new Map(result.blocks.map((block) => [block.id, block])), [result.blocks]);
  const links = result.links.filter((link) => {
    const unitType = primaryUnitType(link, units);
    return (
      (relationFilter === "all" || link.relation === relationFilter) &&
      (unitTypeFilter === "all" || unitType === unitTypeFilter)
    );
  });
  const definitions = new Map(result.relations.map((item) => [item.name, item.description]));

  return (
    <CollapsibleCard
      title="Traceability result"
      subtitle={
        <span>
          {result.reference_document.doc_id}{" "}
          <ArrowRight className="mx-1 inline h-3 w-3" />{" "}
          {result.comparison_document.doc_id}
        </span>
      }
      contentClassName="p-0"
      trailing={
        <FinalResultActions
          onNewAnalysis={onNewAnalysis}
          download={{
            filename: alignerResultFilename({ alignment: result }),
            data: packAlignerResult({ alignment: result }),
          }}
        />
      }
    >
      <div className="flex items-center gap-2 border-b border-border px-5 py-3 sm:px-6">
        <p className="text-xs font-medium text-muted-foreground">Relationship matrix</p>
        <RelationHelp definitions={result.relations} />
      </div>
      <AlignmentMatrix
        links={result.links}
        units={units}
        relationFilter={relationFilter}
        unitTypeFilter={unitTypeFilter}
        definitions={definitions}
        onRelationChange={setRelationFilter}
        onUnitTypeChange={setUnitTypeFilter}
      />

      <div className="flex min-h-11 items-center justify-between gap-4 border-b border-border px-5 py-2.5 text-xs text-muted-foreground">
        <span>Showing {links.length} of {result.links.length} links</span>
        {(relationFilter !== "all" || unitTypeFilter !== "all") && (
          <button
            type="button"
            className="font-medium text-foreground transition-opacity hover:opacity-65"
            onClick={() => { setRelationFilter("all"); setUnitTypeFilter("all"); }}
          >
            Clear filter
          </button>
        )}
      </div>

      <div className="divide-y divide-border">
        {links.map((link) => <AlignmentRow key={link.id} link={link} units={units} blocks={blocks} definition={definitions.get(link.relation)} />)}
        {links.length === 0 && <p className="px-5 py-10 text-center text-sm text-muted-foreground">No links match this filter.</p>}
      </div>
    </CollapsibleCard>
  );
}

function AlignmentMatrix({
  links,
  units,
  relationFilter,
  unitTypeFilter,
  definitions,
  onRelationChange,
  onUnitTypeChange,
}: {
  links: AlignmentLink[];
  units: Map<string, AlignmentUnit>;
  relationFilter: AlignmentRelation | "all";
  unitTypeFilter: AlignmentUnitType | "all";
  definitions: Map<string, string>;
  onRelationChange: (value: AlignmentRelation | "all") => void;
  onUnitTypeChange: (value: AlignmentUnitType | "all") => void;
}) {
  const counts = new Map<string, number>();
  for (const link of links) {
    const unitType = primaryUnitType(link, units);
    if (!unitType) continue;
    const key = `${unitType}:${link.relation}`;
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  const maxCount = Math.max(1, ...counts.values());

  return (
    <div className="border-b border-border px-5 py-5">
      <div className="mb-4">
        <h3 className="text-sm font-semibold tracking-[-0.015em]">Alignment matrix</h3>
        <p className="mt-1 text-xs text-muted-foreground">
          Select a row, column, or cell to inspect its underlying trace.
        </p>
      </div>
      <div className="overflow-x-auto rounded-md border border-border">
        <table className="w-full min-w-[680px] table-fixed border-collapse text-xs">
          <thead>
            <tr className="bg-muted/25">
              <th scope="col" className="w-40 border-b border-r border-border px-3 py-2.5 text-left font-medium text-muted-foreground">
                Unit type
              </th>
              {RELATIONS.map((relation) => {
                const total = links.filter((link) => link.relation === relation).length;
                return (
                  <th key={relation} scope="col" className="border-b border-r border-border p-0 last:border-r-0">
                    <button
                      type="button"
                      title={definitions.get(relation)}
                      onClick={() => onRelationChange(relationFilter === relation ? "all" : relation)}
                      className={cn(
                        "flex w-full items-center justify-between gap-2 px-3 py-2.5 text-left font-medium transition-colors hover:bg-muted/50",
                        relationFilter === relation && "bg-muted/70 text-foreground",
                      )}
                    >
                      <span>{displayLabel(relation)}</span>
                      <span className="tabular-nums text-muted-foreground">{total}</span>
                    </button>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {UNIT_TYPES.map((unitType) => (
              <tr key={unitType}>
                <th scope="row" className="border-b border-r border-border p-0 last:border-b-0">
                  <button
                    type="button"
                    onClick={() => onUnitTypeChange(unitTypeFilter === unitType ? "all" : unitType)}
                    className={cn(
                      "w-full px-3 py-3 text-left font-medium transition-colors hover:bg-muted/50",
                      unitTypeFilter === unitType && "bg-muted/70",
                    )}
                  >
                    {displayLabel(unitType)}
                  </button>
                </th>
                {RELATIONS.map((relation) => {
                  const count = counts.get(`${unitType}:${relation}`) ?? 0;
                  const selected = relationFilter === relation && unitTypeFilter === unitType;
                  return (
                    <td key={relation} className="border-b border-r border-border p-1.5 last:border-r-0">
                      <button
                        type="button"
                        disabled={count === 0}
                        aria-label={`${count} ${displayLabel(relation)} ${displayLabel(unitType)} links`}
                        onClick={() => {
                          if (selected) {
                            onRelationChange("all");
                            onUnitTypeChange("all");
                          } else {
                            onRelationChange(relation);
                            onUnitTypeChange(unitType);
                          }
                        }}
                        style={{ backgroundColor: matrixColor(relation, count, maxCount) }}
                        className={cn(
                          "flex h-9 w-full items-center justify-center rounded text-sm font-semibold tabular-nums transition-[box-shadow,transform] enabled:hover:-translate-y-px enabled:hover:shadow-sm disabled:text-muted-foreground/30",
                          selected && "ring-1 ring-inset ring-foreground/60",
                        )}
                      >
                        {count}
                      </button>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function primaryUnitType(
  link: AlignmentLink,
  units: Map<string, AlignmentUnit>,
): AlignmentUnitType | null {
  const unitId = link.reference_unit_ids[0] ?? link.comparison_unit_ids[0];
  return unitId ? units.get(unitId)?.unit_type ?? null : null;
}

function matrixColor(
  relation: AlignmentRelation,
  count: number,
  maxCount: number,
): string {
  if (count === 0) return "transparent";
  const colors: Record<AlignmentRelation, string> = {
    aligned: "16, 185, 129",
    modified: "245, 158, 11",
    conflict: "239, 68, 68",
    missing: "100, 116, 139",
    introduced: "59, 130, 246",
  };
  const alpha = 0.08 + 0.2 * (count / maxCount);
  return `rgba(${colors[relation]}, ${alpha.toFixed(3)})`;
}

function RelationHelp({ definitions }: { definitions: { name: string; description: string }[] }) {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button type="button" aria-label="Explain alignment relations" className="text-muted-foreground transition-colors hover:text-foreground">
          <CircleHelp className="h-3.5 w-3.5" />
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-80">
        <p className="text-xs font-semibold">Alignment relations</p>
        <dl className="mt-3 space-y-2.5">
          {definitions.map((item) => <div key={item.name}><dt className="text-[11px] font-medium">{displayLabel(item.name)}</dt><dd className="mt-0.5 text-[11px] leading-4 text-muted-foreground">{item.description}</dd></div>)}
        </dl>
      </PopoverContent>
    </Popover>
  );
}

function AlignmentRow({ link, units, blocks, definition }: { link: AlignmentLink; units: Map<string, AlignmentUnit>; blocks: Map<string, ContentBlock>; definition?: string }) {
  const references = link.reference_unit_ids.map((id) => units.get(id)).filter(Boolean) as AlignmentUnit[];
  const comparisons = link.comparison_unit_ids.map((id) => units.get(id)).filter(Boolean) as AlignmentUnit[];
  return (
    <article className="px-5 py-5">
      <div className="flex items-start justify-between gap-4">
        <span title={definition} className={cn("rounded-full border px-2.5 py-1 text-[10px] font-semibold capitalize", RELATION_STYLES[link.relation])}>
          {displayLabel(link.relation)}
        </span>
        <span className="text-[10px] text-muted-foreground">{references[0]?.unit_type ? displayLabel(references[0].unit_type) : comparisons[0]?.unit_type ? displayLabel(comparisons[0].unit_type) : "Unit"}</span>
      </div>
      <div className="mt-4 grid gap-4 md:grid-cols-[1fr_auto_1fr] md:items-start">
        <UnitSide label="Reference" units={references} blocks={blocks} empty="No reference unit" />
        <ArrowRight className="mt-7 hidden h-4 w-4 text-muted-foreground/60 md:block" />
        <UnitSide label="Comparison" units={comparisons} blocks={blocks} empty="No comparison unit" />
      </div>
      <p className="mt-4 text-xs leading-5 text-muted-foreground">{link.reason}</p>
    </article>
  );
}

function UnitSide({ label, units, blocks, empty }: { label: string; units: AlignmentUnit[]; blocks: Map<string, ContentBlock>; empty: string }) {
  return (
    <div className="min-w-0">
      <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">{label}</p>
      {units.length ? units.map((unit) => (
        <div key={unit.id} className="mb-2 last:mb-0">
          <p className="text-sm leading-6">{unit.statement}</p>
          <details className="mt-1 text-[11px] text-muted-foreground">
            <summary className="w-fit cursor-pointer select-none hover:text-foreground">
              {unit.block_ids.length} source block{unit.block_ids.length === 1 ? "" : "s"}
            </summary>
            <div className="mt-2 space-y-2 border-l border-border pl-3">
              {unit.block_ids.map((blockId) => {
                const block = blocks.get(blockId);
                return <div key={blockId}><p className="font-mono text-[10px]">{blockId}</p><p className="mt-0.5 line-clamp-4 leading-5">{block?.content || "Visual source block"}</p></div>;
              })}
            </div>
          </details>
        </div>
      )) : <p className="text-sm italic text-muted-foreground/70">{empty}</p>}
    </div>
  );
}

function FileSlot({ label, helper, file, disabled, onChange }: { label: string; helper: string; file: File | null; disabled: boolean; onChange: (file: File | null) => void }) {
  const input = useRef<HTMLInputElement>(null);
  return (
    <div>
      <div className="mb-2 flex items-baseline justify-between gap-3">
        <Label>{label}</Label><span className="text-[10px] text-muted-foreground">DOCX, PDF, PPTX</span>
      </div>
      <button
        type="button"
        disabled={disabled}
        onClick={() => input.current?.click()}
        onDragOver={(event) => event.preventDefault()}
        onDrop={(event) => { event.preventDefault(); if (!disabled) onChange(event.dataTransfer.files?.[0] ?? null); }}
        className="flex min-h-[76px] w-full items-center gap-3 rounded-md border border-dashed border-input bg-muted/20 px-4 text-left transition-colors hover:border-foreground/25 hover:bg-muted/40 disabled:opacity-50"
      >
        {file ? <Check className="h-4 w-4 shrink-0" /> : <Upload className="h-4 w-4 shrink-0 text-muted-foreground" />}
        <span className="min-w-0"><span className="block truncate text-sm">{file?.name ?? "Choose a document"}</span><span className="mt-1 block text-[11px] text-muted-foreground">{file ? `${(file.size / 1024 / 1024).toFixed(2)} MB` : helper}</span></span>
      </button>
      <input ref={input} type="file" accept=".docx,.pdf,.pptx" className="hidden" onChange={(event) => onChange(event.target.files?.[0] ?? null)} />
    </div>
  );
}

function ConfigField({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="min-w-0"><Label className="mb-2 block">{label}</Label>{children}</div>;
}

function ConfigSelect({ value, options, disabled, onChange }: { value: string; options: { value: string; label: string }[]; disabled?: boolean; onChange: (value: string) => void }) {
  return <Select value={value} onValueChange={onChange} disabled={disabled}><SelectTrigger><SelectValue placeholder="Select" /></SelectTrigger><SelectContent>{options.map((option) => <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>)}</SelectContent></Select>;
}

function unique(values: string[]) { return Array.from(new Set(values)).sort(); }
