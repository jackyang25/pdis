"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, ArrowRight, CircleDashed, Plus, X } from "lucide-react";
import { RunHistory } from "@/components/run-history";
import { CollapsibleCard } from "@/components/collapsible-card";
import { ErrorMessage } from "@/components/ui/error-message";
import {
  DocumentSourceProvider,
  DocumentSourceTrace,
} from "@/components/document-source-trace";
import { FinalResultActions } from "@/components/final-result-actions";
import { PageHeader } from "@/components/page-header";
import { RunPanel, type DocumentSlot } from "@/components/run-panel";
import {
  ContextFields,
  SourceTypeField,
  useSupportedDocumentTypes,
} from "@/components/configuration-fields";
import { ConfigurationShell } from "@/components/ui/config-field";
import { AlignerDocumentTrace } from "@/components/aligner-document-trace";
import { AlignerSignalHelp, AlignerSignalLabel } from "@/components/aligner-signal-help";
import { PriorityPanel } from "@/components/ui/priority-panel";
import { SectionHeading } from "@/components/ui/section-heading";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  ALIGNMENT_VERDICTS,
  VERDICT_LABELS,
  fetchAlignerEdges,
  runAligner,
  type AlignmentEdge,
  type AlignmentEdgeSpec,
  type AlignmentFinding,
  type AlignmentResult,
  type AlignmentVerdict,
} from "@/lib/api";
import { chainWarningText, chainWarnings, type ChainWarning } from "@/lib/aligner-chain";
import {
  ALIGNER_EMPTY_MESSAGE,
  ALIGNER_ORDER_NOTE,
  comparisonLabel,
  countVerdicts,
  findingsByComparison,
  findingsWithVerdict,
  selectAlignerPriorities,
} from "@/lib/aligner-priorities";
import {
  alignerResultFilename,
  packAlignerResult,
  runLabel,
  splitResultContext,
  unpackAlignerResult,
  readResultIdentity,
} from "@/lib/result-file";
import { usePriorityDigest } from "@/lib/priority-digest";
import { toolAuthority } from "@/lib/tools";
import { useAlignerSession } from "@/lib/session";
import { isContextComplete, useHeaderStore } from "@/lib/store";
import { displayLabel } from "@/lib/display-label";

const STEPS = [
  { key: "parse", label: "Parsing documents" },
  { key: "requirements", label: "Reading requirements" },
  { key: "compare", label: "Comparing" },
];

/** A document the user has added but may not have chosen a type for yet. */
type DocumentChoice = { key: string; sourceType: string };

const INITIAL_CHOICES: DocumentChoice[] = [
  { key: "d1", sourceType: "" },
  { key: "d2", sourceType: "" },
];

export default function AlignerPage() {
  const session = useAlignerSession();
  // Context comes from the shared store like every other tool, so a choice made
  // on Inspector or Scout is still there when the user arrives here. Only the
  // per-document types are Aligner's own, because only their count differs.
  const header = useHeaderStore((state) => state.header);
  const [declaredEdges, setDeclaredEdges] = useState<AlignmentEdgeSpec[]>([]);
  const [choices, setChoices] = useState<DocumentChoice[]>(INITIAL_CHOICES);
  const [showSetup, setShowSetup] = useState(!session.result);
  const importRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (session.result) setShowSetup(false);
  }, [session.result]);

  useEffect(() => {
    // Surfaced rather than swallowed: without the declared comparisons nothing
    // can resolve, so Run would gate with no way for the user to learn why.
    fetchAlignerEdges()
      .then(setDeclaredEdges)
      .catch((error: Error) =>
        session.setError(`Could not load the comparisons Aligner makes: ${error.message}`),
      );
  }, [session.setError]);

  // A type chosen under one context does not exist under another, so changing
  // either clears the document rows rather than leaving a stale selection.
  useEffect(() => {
    setChoices(INITIAL_CHOICES);
  }, [header.org, header.intervention_class]);

  const chosen = choices.map((choice) => choice.sourceType).filter(Boolean);
  // Every declared comparison whose two documents are both present. This is the
  // same rule the service applies, read from the same config it publishes, so the
  // preview cannot promise a comparison the run will not make.
  const comparisons = declaredEdges.filter(
    (edge) => chosen.includes(edge.reference) && chosen.includes(edge.comparison),
  );

  const slots: readonly DocumentSlot[] = chosen.map((sourceType) => ({
    id: sourceType,
    label: displayLabel(sourceType),
  }));
  const contextReady = isContextComplete(header);
  const configured = contextReady && chosen.length >= 2 && comparisons.length > 0;

  async function handleRun(files: Record<string, File>) {
    if (!configured || !contextReady) return;
    session.setBusy(true);
    session.setError(null);
    session.setStage(null);
    session.setProgress(null);
    try {
      const result = await runAligner(
        // Read from the slots this page declared, never from every file the panel
        // is holding: a type the user switched away from may still have one.
        chosen.map((sourceType) => ({ file: files[sourceType], sourceType })),
        {
          org: header.org,
          intervention_class: header.intervention_class,
          indication: header.indication,
        },
        (stage, progress) => {
          session.setStage(stage);
          session.setProgress(progress ?? null);
        },
      );
      session.addResult(result);
    } catch (error) {
      session.setError((error as Error).message);
    } finally {
      session.setBusy(false);
    }
  }

  async function handleImport(file: File) {
    session.setError(null);
    try {
      const raw = JSON.parse(await file.text());
      session.addResult(unpackAlignerResult(raw), readResultIdentity(raw));
    } catch (error) {
      session.setError(`Could not import result: ${(error as Error).message}`);
    }
  }

  return (
    <>
      <PageHeader
        title="Aligner"
        description="The iTPP, cTPP, and IPDP against each other: whether the candidate and the plan deliver what was asked for."
      />
      <div className="flex flex-col gap-6">
        {(!session.result || showSetup) && (
          <RunPanel
            busy={session.busy}
            documents={slots}
            onRun={(files) => void handleRun(files)}
            steps={STEPS}
            currentStage={session.stage}
            progress={session.progress}
            runDisabled={!configured}
            hint={runHint(contextReady, chosen, comparisons, declaredEdges)}
            runLabel="Run alignment"
            busyLabel="Aligning"
            configuration={
              <ConfigurationShell>
                <ContextFields />
                <DocumentChooser
                  choices={choices}
                  disabled={!contextReady}
                  onChange={setChoices}
                />
                <ComparisonPreview
                  comparisons={comparisons}
                  chosen={chosen}
                  declared={declaredEdges}
                />
              </ConfigurationShell>
            }
            extraControls={
              <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                <span>Or view a previously downloaded result:</span>
                <button
                  type="button"
                  onClick={() => importRef.current?.click()}
                  disabled={session.busy}
                  className="font-medium text-primary hover:text-primary/80 disabled:opacity-50"
                >
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
            }
          />
        )}

        {session.error && <ErrorMessage>{session.error}</ErrorMessage>}
        {session.result && (
          <AlignmentView
            result={session.result.alignment}
            onNewAnalysis={() => setShowSetup(true)}
          />
        )}
      </div>
    </>
  );
}

/**
 * Which documents this run holds.
 *
 * Each row offers only the types no other row has taken, so two documents of the
 * same type - which the service refuses - cannot be selected in the first place.
 * A rule enforced by the options is one the user never has to read an error about.
 */
function DocumentChooser({
  choices,
  disabled,
  onChange,
}: {
  choices: DocumentChoice[];
  disabled?: boolean;
  onChange: (next: DocumentChoice[]) => void;
}) {
  // Only to cap the rows: a run cannot hold more documents than there are types,
  // because each type may appear once. The options themselves are the shared
  // field's business, not this component's.
  const { types } = useSupportedDocumentTypes();
  const available = new Set((types ?? []).map((item) => item.source_type)).size;
  const taken = choices.map((choice) => choice.sourceType).filter(Boolean);
  const canAdd = !disabled && choices.length < available;

  return (
    <div className="mt-4">
      <div className="mt-1 flex flex-col gap-3">
        {choices.map((choice, index) => (
          <SourceTypeField
            key={choice.key}
            label={`Document ${index + 1}`}
            value={choice.sourceType || undefined}
            exclude={taken}
            // Once, under the first row: the note is about what the field does,
            // not about one document, so repeating it per row is noise.
            hint={index === 0}
            // Handed to the field rather than placed beside it, so it lines up with
            // the select. Beside it, the button aligned to the bottom of the row —
            // which on the row carrying the help text put it next to the prose.
            action={
              <button
                type="button"
                aria-label={`Remove document ${index + 1}`}
                disabled={disabled || choices.length <= 2}
                onClick={() =>
                  onChange(choices.filter((_, position) => position !== index))
                }
                className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground disabled:pointer-events-none disabled:opacity-30 motion-reduce:transition-none"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            }
            onChange={(value) =>
              onChange(
                choices.map((item, position) =>
                  position === index ? { ...item, sourceType: value } : item,
                ),
              )
            }
          />
        ))}
      </div>
      <button
        type="button"
        disabled={!canAdd}
        onClick={() =>
          onChange([...choices, { key: `d${Date.now()}`, sourceType: "" }])
        }
        className="mt-2.5 flex items-center gap-1.5 text-xs font-medium text-primary transition-opacity hover:opacity-75 disabled:pointer-events-none disabled:opacity-40 motion-reduce:transition-none"
      >
        <Plus className="h-3.5 w-3.5" />
        Add document
      </button>
    </div>
  );
}

/**
 * What the run will actually compare, shown before it runs.
 *
 * Read from the service's own declared comparisons rather than a list restated
 * here, so the preview and the run cannot disagree.
 */
function ComparisonPreview({
  comparisons,
  chosen,
  declared,
}: {
  comparisons: AlignmentEdgeSpec[];
  chosen: string[];
  declared: AlignmentEdgeSpec[];
}) {
  if (chosen.length < 2) return null;

  return (
    <div className="mt-5 border-t border-border pt-4">
      <p className="text-xs font-medium">Comparisons</p>
      {comparisons.length > 0 ? (
        <ul className="mt-2 flex flex-col gap-2.5">
          {comparisons.map((edge) => (
            <li key={`${edge.reference}-${edge.comparison}`}>
              <p className="flex items-center gap-1.5 text-xs font-medium">
                <span>{displayLabel(edge.reference)}</span>
                <ArrowRight aria-label="compared against" className="h-3 w-3 text-muted-foreground" />
                <span>{displayLabel(edge.comparison)}</span>
              </p>
              <p className="mt-0.5 text-[11px] leading-4 text-muted-foreground">
                {edge.question}
              </p>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-[11px] leading-4 text-muted-foreground">
          These documents form no comparison. Aligner compares{" "}
          {declared
            .map((edge) => `${displayLabel(edge.reference)} to ${displayLabel(edge.comparison)}`)
            .join(", ")}
          .
        </p>
      )}
    </div>
  );
}

/** Why Run is gated, naming the one thing still missing. */
function runHint(
  contextReady: boolean,
  chosen: string[],
  comparisons: AlignmentEdgeSpec[],
  declared: AlignmentEdgeSpec[],
): string | undefined {
  if (!contextReady) return "Complete the configuration to run.";
  if (chosen.length < 2) return "Choose a type for at least two documents.";
  if (declared.length > 0 && comparisons.length === 0) {
    return "These documents form no comparison.";
  }
  return undefined;
}

/**
 * What a run produces today: every document, parsed and citable.
 *
 * The matrix, relation filters, and link rows that used to live here were removed
 * with the analysis behind them. `DocumentSourceProvider` stays because it is what
 * makes any future finding resolvable to its source passage.
 */
function AlignmentView({
  result,
  onNewAnalysis,
}: {
  result: AlignmentResult;
  onNewAnalysis: () => void;
}) {
  const {
    results,
    selectedId: selectedRunId,
    selectResult,
    removeResult,
  } = useAlignerSession();
  // Same handoff every tool uses: a citation anywhere opens that passage in the trace,
  // so the two views are one navigation rather than two places to look.
  const [resultTab, setResultTab] = useState("comparisons");
  const [traceFocusBlockId, setTraceFocusBlockId] = useState<string | null>(null);
  const openBlockInTrace = useCallback((blockId: string) => {
    setTraceFocusBlockId(blockId);
    setResultTab("trace");
  }, []);
  const consumeTraceFocus = useCallback((blockId: string) => {
    setTraceFocusBlockId((current) => (current === blockId ? null : current));
  }, []);

  const counts = useMemo(() => countVerdicts(result), [result]);
  const groups = useMemo(() => findingsByComparison(result), [result]);
  const priorities = useMemo(() => selectAlignerPriorities(result), [result]);
  const selectedId = useAlignerSession((state) => state.selectedId);
  const digest = usePriorityDigest(
    selectedId
      ? {
          resultId: selectedId,
          authority: toolAuthority("aligner"),
          orderNote: ALIGNER_ORDER_NOTE,
          items: priorities,
          analysis: splitResultContext(result).analysis,
          blockIds: result.blocks.map((block) => block.id),
          org: result.org,
          interventionClass: result.intervention_class,
          indication: result.indication,
        }
      : null,
  );
  // Where two comparisons meet. Computed once per result and read per row, so the panel
  // and the rows cannot disagree about which passages an earlier comparison flagged.
  const warnings = useMemo(() => chainWarnings(result), [result]);
  const subtitle = [
    `${result.edges.length} ${result.edges.length === 1 ? "comparison" : "comparisons"}`,
    displayLabel(result.intervention_class),
    result.documents.map((document) => displayLabel(document.source_type)).join(", "),
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <CollapsibleCard
      title="Alignment"
      subtitle={subtitle}
      defaultOpen
      contentClassName="px-0 py-0 sm:px-0"
      trailing={
        <>
        <RunHistory
          runs={results}
          selectedId={selectedRunId}
          onSelect={selectResult}
          onRemove={removeResult}
          label={(value) => runLabel(value, "aligner")}
        />
        <FinalResultActions
          onNewAnalysis={onNewAnalysis}
          download={{
            filename: alignerResultFilename({ alignment: result }),
            data: packAlignerResult({ alignment: result }),
          }}
        />
        </>
      }
    >
      <DocumentSourceProvider blocks={result.blocks} onOpenInTrace={openBlockInTrace}>
        <Tabs value={resultTab} onValueChange={setResultTab} className="w-full">
          <div className="flex items-center justify-between gap-3 border-b border-border px-5 pt-2 sm:px-6">
            <TabsList className="justify-start border-b-0">
              {/*
                Comparisons first: a tool opens on what it is about. Aligner is about
                what one document does with another's requirements, and the documents
                are what it read to decide.
              */}
              <TabsTrigger value="comparisons">Comparisons</TabsTrigger>
              <TabsTrigger value="trace">Documents</TabsTrigger>
            </TabsList>
            <AlignerSignalHelp />
          </div>

          <TabsContent value="comparisons" className="m-0">
            <div className="flex flex-col gap-6 px-5 py-5 sm:px-6">
              <CountRow counts={counts} />

              <PriorityPanel
                attribution="by Aligner"
                items={priorities}
                emptyMessage={ALIGNER_EMPTY_MESSAGE}
                orderNote={ALIGNER_ORDER_NOTE}
                digest={digest?.state === "ready" ? digest.digest.digest : undefined}
                nominations={digest?.state === "ready" ? digest.digest.nominations : []}
                digestLoading={digest?.state === "loading"}
                digestError={digest?.state === "failed" ? digest.reason : undefined}
              />

              <div className="space-y-3">
                <SectionHeading
                  title={
                    <>
                      Comparisons{" "}
                      <span className="tabular-nums text-muted-foreground">
                        {result.edges.length}
                      </span>
                    </>
                  }
                  description="Each comparison runs one way: the first document sets the requirements and the second is measured against them. Open one to see every requirement it asked, grouped by what the other document does with it."
                />
                {groups.map(({ edge, findings }) => (
                  <ComparisonCard
                    key={edge.edge_id}
                    edge={edge}
                    findings={findings}
                    result={result}
                    warnings={warnings}
                  />
                ))}
              </div>
            </div>
          </TabsContent>

          <TabsContent value="trace" className="m-0">
            <AlignerDocumentTrace
              result={result}
              focusBlockId={traceFocusBlockId}
              onFocusBlockConsumed={consumeTraceFocus}
            />
          </TabsContent>
        </Tabs>
      </DocumentSourceProvider>
    </CollapsibleCard>
  );
}

/**
 * The five verdicts, always all five.
 *
 * Every one is a number a model produced, so a zero is information: it says the check
 * ran and found nothing of that kind. Hiding one would make a run where nothing fell
 * short look like a run with no such concept — and the figures would still sum to the
 * total, so nothing would look wrong.
 */
function CountRow({ counts }: { counts: Record<AlignmentVerdict, number> }) {
  const total = ALIGNMENT_VERDICTS.reduce((sum, verdict) => sum + counts[verdict], 0);
  return (
    <div className="flex flex-wrap items-baseline gap-x-6 gap-y-2">
      <p className="text-xs">
        <AlignerSignalLabel topic="denominator">
          <span className="font-medium">
            {total} {total === 1 ? "requirement" : "requirements"}
          </span>
        </AlignerSignalLabel>
      </p>
      {ALIGNMENT_VERDICTS.map((verdict) => (
        <p key={verdict} className="text-xs text-muted-foreground">
          <span className="tabular-nums text-foreground">{counts[verdict]}</span>{" "}
          {VERDICT_LABELS[verdict].toLowerCase()}
        </p>
      ))}
    </div>
  );
}

/**
 * One comparison, its question, and its requirements grouped by verdict.
 *
 * Grouped by verdict inside the comparison rather than listed flat, because the
 * question a reader arrives with is "what falls short here" and a flat list of forty
 * requirements answers it only after forty reads. Shortfalls lead for the same reason.
 */
function ComparisonCard({
  edge,
  findings,
  result,
  warnings,
}: {
  edge: AlignmentEdge;
  findings: AlignmentFinding[];
  result: AlignmentResult;
  warnings: Map<string, ChainWarning[]>;
}) {
  return (
    <CollapsibleCard
      title={comparisonLabel(edge, result)}
      subtitle={edge.question}
      // Closed, like Inspector's sections and Expert's disciplines. The panel above
      // already carries everything a reader has to act on; this is the full
      // enumeration, and open it puts forty requirements between them and the second
      // comparison. The row still states which comparison it is, what it asks, and how
      // many requirements it holds.
      defaultOpen={false}
      trailing={
        <span className="shrink-0 text-[11px] tabular-nums text-muted-foreground">
          {findings.length} {findings.length === 1 ? "requirement" : "requirements"}
        </span>
      }
    >
      <div className="flex flex-col gap-4">
        {VERDICT_ORDER.map((verdict) => {
          const inVerdict = findingsWithVerdict(findings, verdict);
          if (inVerdict.length === 0) return null;
          return (
            <section key={verdict}>
              <p className="text-xs font-medium">
                <AlignerSignalLabel topic="verdict">
                  {VERDICT_LABELS[verdict]}
                </AlignerSignalLabel>{" "}
                <span className="tabular-nums text-muted-foreground">
                  {inVerdict.length}
                </span>
              </p>
              <ul className="mt-2 flex flex-col gap-3">
                {inVerdict.map((finding) => (
                  <FindingRow
                    key={finding.requirement_id}
                    finding={finding}
                    warnings={warnings.get(finding.requirement_id) ?? []}
                  />
                ))}
              </ul>
            </section>
          );
        })}
      </div>
    </CollapsibleCard>
  );
}

/**
 * Reading order inside a comparison, which is not the vocabulary's own order.
 *
 * What a PPL came for goes first. `ALIGNMENT_VERDICTS` is ordered by distance from the
 * bar because that is how the vocabulary is defined; this is ordered by what is
 * actionable, and the two are deliberately separate so neither has to compromise.
 */
const VERDICT_ORDER: AlignmentVerdict[] = [
  "falls_short",
  "not_comparable",
  "not_addressed",
  "exceeds",
  "meets",
];

/** One requirement, what the measured document says about it, and both lineages. */
function FindingRow({
  finding,
  warnings,
}: {
  finding: AlignmentFinding;
  /** What an earlier comparison already said about the passage this delivers. */
  warnings: ChainWarning[];
}) {
  return (
    <li className="rounded-md border border-border/70 px-3 py-2.5">
      <p className="text-xs font-medium leading-5">
        <AlignerSignalLabel topic="requirement">{finding.requirement}</AlignerSignalLabel>
      </p>
      <p className="mt-1.5 text-xs leading-5 text-muted-foreground">
        {finding.statement}
      </p>
      {finding.gap && (
        <p className="mt-1.5 flex items-start gap-1.5 text-xs leading-5 text-foreground/85">
          <CircleDashed aria-hidden="true" className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          <span>
            <span className="text-muted-foreground">Still to close: </span>
            {finding.gap}
          </span>
        </p>
      )}
      {warnings.map((warning) => (
        <p
          key={warning.upstreamRequirementId}
          className="mt-1.5 flex items-start gap-1.5 text-xs leading-5 text-[hsl(var(--tone-warning))]"
        >
          <AlertTriangle aria-hidden="true" className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          {/*
            A claim about the passage, not about the requirement: the two comparisons
            cite the same block, which does not prove they mean the same clause of it.
            True either way, and it sends a reader to the right place.
          */}
          <span>{chainWarningText(warning)}</span>
        </p>
      ))}
      <div className="mt-2 grid gap-2 sm:grid-cols-2">
        <div className="min-w-0">
          <p className="text-[11px] text-muted-foreground">Requirement stated in</p>
          <DocumentSourceTrace blockIds={finding.reference_block_ids} />
        </div>
        {finding.comparison_block_ids.length > 0 && (
          <div className="min-w-0">
            <p className="text-[11px] text-muted-foreground">Read from</p>
            <DocumentSourceTrace blockIds={finding.comparison_block_ids} />
          </div>
        )}
      </div>
    </li>
  );
}
