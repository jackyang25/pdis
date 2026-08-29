"use client";

import { ResultLayout } from "@/components/ui/result-layout";
import { DisclosureRow } from "@/components/ui/disclosure-row";

import { MetricsRow } from "@/components/ui/metrics-row";
import {
  ResultToolbar,
  ResultToolbarEnd,
} from "@/components/ui/result-toolbar";
import { VerdictCounts } from "@/components/ui/verdict-counts";
import { useTraceFocus } from "@/lib/trace-focus";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, ArrowRight, Plus, X } from "lucide-react";
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
import {
  AlignerSignalHelp,
  AlignerSignalLabel,
} from "@/components/aligner-signal-help";
import { PriorityPanel } from "@/components/ui/priority-panel";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  ALIGNMENT_VERDICTS,
  ALIGNMENT_VERDICT_TONE,
  VERDICT_LABELS,
  fetchAlignerEdges,
  runAligner,
  type AlignmentEdge,
  type AlignmentEdgeSpec,
  type AlignmentFinding,
  type AlignerResponse,
  type AlignmentResult,
  type AlignmentVerdict,
  spanBlockIds,
} from "@/lib/api";
import {
  chainWarningText,
  chainWarnings,
  type ChainWarning,
} from "@/lib/aligner-chain";
import {
  ALIGNER_EMPTY_MESSAGE,
  ALIGNER_ORDER_NOTE,
  comparisonLabel,
  documentName,
  countVerdicts,
  findingsByComparison,
  findingsWithVerdict,
  selectAlignerPriorities,
} from "@/lib/aligner-priorities";
import {
  alignerResultFilename,
  packAlignerResult,
  runLabel,
  runScope,
  splitResultContext,
  unpackAlignerResult,
  readResultIdentity,
} from "@/lib/result-file";
import { usePriorityDigest } from "@/lib/priority-digest";
import { toolAuthority } from "@/lib/tools";
import { useAlignerSession } from "@/lib/session";
import { isContextComplete, useHeaderStore } from "@/lib/store";
import { displayLabel } from "@/lib/display-label";
import { Quoted, Reading } from "@/components/ui/evidence-text";
import { SignalChip } from "@/components/ui/signal-chip";

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
        session.setError(
          `Could not load the comparisons Aligner makes: ${error.message}`,
        ),
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
    (edge) =>
      chosen.includes(edge.reference) && chosen.includes(edge.comparison),
  );

  const slots: readonly DocumentSlot[] = chosen.map((sourceType) => ({
    id: sourceType,
    label: displayLabel(sourceType),
  }));
  const contextReady = isContextComplete(header);
  const configured =
    contextReady && chosen.length >= 2 && comparisons.length > 0;

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
        description="The iTPP, cTPP, and IPDP against each other: whether each honours the one before it, requirement by requirement. Coherence, not feasibility — whether the documented plan supports the documented objectives, never whether those objectives are achievable."
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
            // The envelope, not the alignment inside it - the same shape Inspector,
            // Screener and Scout hand their views. `runLabel` and `runScope` read a saved
            // result, and a saved Aligner result is `{ alignment: ... }`; handed the
            // inner object they read `undefined.documents` and the page threw.
            result={session.result}
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
                <ArrowRight
                  aria-label="compared against"
                  className="h-3 w-3 text-muted-foreground"
                />
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
            .map(
              (edge) =>
                `${displayLabel(edge.reference)} to ${displayLabel(edge.comparison)}`,
            )
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
  result: AlignerResponse;
  onNewAnalysis: () => void;
}) {
  // Unwrapped once, here, rather than at the call site. The view needs both: the
  // envelope for the readers that identify a saved run, and the alignment for
  // everything about its content.
  const alignment = result.alignment;
  const {
    results,
    selectedId: selectedRunId,
    selectResult,
    removeResult,
  } = useAlignerSession();
  // Same handoff every tool uses: a citation anywhere opens that passage in the trace,
  // so the two views are one navigation rather than two places to look.
  const [resultTab, setResultTab] = useState("comparisons");
  const revealTrace = useCallback(() => setResultTab("trace"), []);
  const {
    focus: traceFocus,
    open: openBlockInTrace,
    consume: consumeTraceFocus,
  } = useTraceFocus(revealTrace);

  const counts = useMemo(() => countVerdicts(alignment), [alignment]);
  const groups = useMemo(() => findingsByComparison(alignment), [alignment]);
  const priorities = useMemo(() => selectAlignerPriorities(alignment), [alignment]);
  const selectedId = useAlignerSession((state) => state.selectedId);
  const digest = usePriorityDigest(
    selectedId
      ? {
          resultId: selectedId,
          authority: toolAuthority("aligner"),
          orderNote: ALIGNER_ORDER_NOTE,
          items: priorities,
          analysis: splitResultContext(result).analysis,
          blockIds: alignment.blocks.map((block) => block.id),
          org: alignment.org,
          interventionClass: alignment.intervention_class,
          indication: alignment.indication,
        }
      : null,
  );
  // Where two comparisons meet. Computed once per result and read per row, so the panel
  // and the rows cannot disagree about which passages an earlier comparison flagged.
  const warnings = useMemo(() => chainWarnings(alignment), [alignment]);

  return (
    <ResultLayout
      title={runLabel(result, "aligner")}
      subtitle={runScope(result, "aligner")}
      // Run-wide, so it holds on the Documents tab too. It was inside the Comparisons tab.
      metrics={<CountRow counts={counts} />}
      metricsNote="Every requirement in the rubric by verdict, including the classes nothing fell into. A zero says the class was checked, not that it was skipped."

      tabValue={resultTab}
      onTabChange={setResultTab}
      tabs={
        <>
          {/*
            Comparisons first: a tool opens on what it is about. Aligner is about
            what one document does with another's requirements, and the documents
            are what it read to decide.
          */}
          <TabsTrigger value="comparisons">Comparisons</TabsTrigger>
          <TabsTrigger value="trace">Documents</TabsTrigger>
        </>
      }
      priorities={{
        // Every item links to a requirement, so it shows where the comparisons are.
        tab: "comparisons",
        panel: (
          <PriorityPanel
            attribution="by Aligner"
            items={priorities}
            emptyMessage={ALIGNER_EMPTY_MESSAGE}
            orderNote={ALIGNER_ORDER_NOTE}
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
            selectedId={selectedRunId}
            onSelect={selectResult}
            onRemove={removeResult}
            label={(value) => runLabel(value, "aligner")}
          />
          <FinalResultActions
            onNewAnalysis={onNewAnalysis}
            download={{
              filename: alignerResultFilename(result),
              data: packAlignerResult(result),
            }}
          />
        </>
      }
    >
      <DocumentSourceProvider
        blocks={alignment.blocks}
        onOpenInTrace={openBlockInTrace}
      >
        <TabsContent value="comparisons" className="m-0">
          {/* The view's nav: its name, and what explains it. */}
          {/* One band, not a band and a heading beneath it. The word "Comparisons"
              appeared three times in a hundred pixels - as the toolbar's label, as a
              section heading, and again in the paragraph under it - and that paragraph
              said what "How to read" three inches to its right already explains. */}
          <ResultToolbar>
            {/* Named again, though the tab says the same word, because the priorities
                panel sits between the two: a reader arrives here past a band about
                something else, and this re-anchors what the rows below are. A toolbar is
                never only its right-hand end - a band holding one link reads as an empty
                strip - so the choice is this word or a control, and there is nothing here
                to filter.

                No count, though. This band does not filter, so a number is not telling a
                reader how much of the result they are seeing; it counted the one or two
                cards directly beneath it, each already titled. */}
            <p className="min-w-0 flex-1 text-xs font-medium text-foreground">
              Comparisons
            </p>
            <ResultToolbarEnd>
              <AlignerSignalHelp />
            </ResultToolbarEnd>
          </ResultToolbar>
          <div className="flex flex-col gap-6 px-5 py-5 sm:px-6">
            <div className="space-y-3">
              {groups.map(({ edge, findings }) => (
                <ComparisonCard
                  key={edge.edge_id}
                  edge={edge}
                  findings={findings}
                  result={alignment}
                  warnings={warnings}
                />
              ))}
            </div>
          </div>
        </TabsContent>

        <TabsContent value="trace" className="m-0">
          <AlignerDocumentTrace
            result={alignment}
            focus={traceFocus}
            onFocusConsumed={consumeTraceFocus}
          />
        </TabsContent>
      </DocumentSourceProvider>
    </ResultLayout>
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
  const total = ALIGNMENT_VERDICTS.reduce(
    (sum, verdict) => sum + counts[verdict],
    0,
  );
  return (
    <MetricsRow
      total={total}
      unit={["requirement", "requirements"]}
      // Every verdict, including zeros: the denominator is the whole rubric, so a zero
      // says the requirement class was checked and nothing fell into it.
      items={ALIGNMENT_VERDICTS.map((verdict) => ({
        label: VERDICT_LABELS[verdict],
        count: counts[verdict],
        tone: ALIGNMENT_VERDICT_TONE[verdict],
      }))}
    />
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
      // Closed, like Inspector's sections and Screener's disciplines. The panel above
      // already carries everything a reader has to act on; this is the full
      // enumeration, and open it puts forty requirements between them and the second
      // comparison. The row still states which comparison it is, what it asks, and how
      // many requirements it holds.
      defaultOpen={false}
      trailing={
        <span className="shrink-0 text-[11px] tabular-nums text-muted-foreground">
          {findings.length}{" "}
          {findings.length === 1 ? "requirement" : "requirements"}
        </span>
      }
    >
      <div className="flex flex-col gap-4">
        {VERDICT_ORDER.map((verdict) => {
          const inVerdict = findingsWithVerdict(findings, verdict);
          if (inVerdict.length === 0) return null;
          return (
            // Closable, the shape Scout's relation groups use. The heading was a bare
            // chip over an open list, so a reader who came for the six shortfalls
            // scrolled the forty-seven requirements that were fine to reach the next
            // group. Open by default: this tab exists to show these, and five closed
            // rows would be a second navigation step to what was already navigated to.
            //
            // No help icon on the heading. It was the same tooltip five times, and an
            // icon on "Falls short" cannot say how it differs from "Not comparable" -
            // which is the thing a reader gets wrong. "How to read" shows all five
            // together and is the only place they can be told apart.
            <DisclosureRow
              key={verdict}
              label={VERDICT_LABELS[verdict]}
              tone={ALIGNMENT_VERDICT_TONE[verdict]}
              count={inVerdict.length}
              defaultOpen
            >
              <ul className="divide-y divide-border/60">
                {inVerdict.map((finding) => (
                  <FindingRow
                    key={finding.requirement_id}
                    finding={finding}
                    warnings={warnings.get(finding.requirement_id) ?? []}
                    referenceName={documentName(edge.reference_doc_id, result)}
                    comparisonName={documentName(edge.comparison_doc_id, result)}
                  />
                ))}
              </ul>
            </DisclosureRow>
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
/**
 * One model sentence, and the document it was read out of.
 *
 * Aligner's row holds two of these - the bar from one document, the answer from the
 * other - and they are deliberately parallel so the difference between them is legible:
 * "24-36 wks" beside "at least 28 weeks". Both are a model's reading, so the authorship
 * mark cannot separate them and neither can tone.
 *
 * The document can. It used to sit at the bottom of the row on two triggers that both
 * read "In document", so a reader met two near-identical sentences and learned which was
 * which only after reading both. The name leads the line instead.
 */
function Attributed({
  document,
  children,
  trigger,
}: {
  document: string;
  children: React.ReactNode;
  /** The passages this line was read from, opened in the trace. */
  trigger?: React.ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-baseline gap-x-2">
      <span className="shrink-0 text-[11px] font-medium text-muted-foreground">
        {document}
      </span>
      <Reading size="prominent" className="mt-0 min-w-0 flex-1">
        {children}
      </Reading>
      {trigger}
    </div>
  );
}

function FindingRow({
  finding,
  warnings,
  referenceName,
  comparisonName,
}: {
  finding: AlignmentFinding;
  /** What an earlier comparison already said about the passage this delivers. */
  warnings: ChainWarning[];
  /** The document that sets the bar, and the one measured against it. */
  referenceName: string;
  comparisonName: string;
}) {
  return (
    // No border. This sat inside a verdict group inside a collapsible card inside a
    // tab, so a requirement was the fourth box a reader counted down - the nesting
    // Inspector lost when a unit stopped being a disclosure. The dividers between rows
    // do the separating a border was doing.
    <li className="py-3 first:pt-0 last:pb-0">
      {/* No help affordance on the row. It repeated on every one of sixty-nine, and an
          icon on one requirement cannot say how a requirement differs from a verdict -
          which is the thing a reader gets wrong. "How to read" explains both together,
          and the group heading above still carries the one for verdicts. */}
      {/* Both lines are a model's sentence, and that is the point of the row: the bar as
          the model read it out of one document, and the answer as it read it out of the
          other. Neither is a quotation - the extractor is asked for "one short sentence
          stating the requirement in the document's own terms", which is its own words
          carrying the document's numbers - so a left rule here would claim a verbatimness
          the pipeline never promised.

          What separates them is therefore not authorship but *which document*, and that
          is what the row now leads each line with. It used to sit at the bottom, on two
          triggers that both read "In document", so a reader met two near-identical
          sentences and learned which was which only after both. */}
      <Attributed
        document={referenceName}
        trigger={
          <DocumentSourceTrace
            blockIds={spanBlockIds(finding.reference_spans)}
            spans={finding.reference_spans}
          />
        }
      >
        {finding.requirement}
      </Attributed>
      {/* Empty on `not_addressed`, where there is nothing to describe: the sentence was
          the verdict again, under a heading that already names the requirement. Rendered
          anyway it would be a mark with nothing after it - and the document line above it
          would then be a name attached to silence. */}
      {finding.statement && (
        <Attributed
          document={comparisonName}
          trigger={
            finding.comparison_spans.length > 0 ? (
              <DocumentSourceTrace
                blockIds={spanBlockIds(finding.comparison_spans)}
                spans={finding.comparison_spans}
              />
            ) : undefined
          }
        >
          {finding.statement}
        </Attributed>
      )}
      {warnings.map((warning) => (
        <p
          key={warning.upstreamRequirementId}
          className="mt-1.5 flex items-start gap-1.5 text-xs leading-5 text-[hsl(var(--tone-warning))]"
        >
          <AlertTriangle
            aria-hidden="true"
            className="mt-0.5 h-3.5 w-3.5 shrink-0"
          />
          {/*
            A claim about the passage, not about the requirement: the two comparisons
            cite the same block, which does not prove they mean the same clause of it.
            True either way, and it sends a reader to the right place.
          */}
          <span>{chainWarningText(warning)}</span>
        </p>
      ))}

    </li>
  );
}
