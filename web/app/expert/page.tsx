"use client";

import { ResultLayout } from "@/components/ui/result-layout";
import {
  ResultToolbar,
  ResultToolbarEnd,
} from "@/components/ui/result-toolbar";
import { useTraceFocus } from "@/lib/trace-focus";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, ChevronDown, Paperclip, Plus, X } from "lucide-react";
import { RunHistory } from "@/components/run-history";
import { CollapsibleCard } from "@/components/collapsible-card";
import {
  DocumentSourceProvider,
  DocumentSourceTrace,
} from "@/components/document-source-trace";
import { ErrorMessage } from "@/components/ui/error-message";
import {
  ExpertSignalHelp,
  ExpertSignalLabel,
} from "@/components/expert-signal-help";
import { FinalResultActions } from "@/components/final-result-actions";
import { PageHeader } from "@/components/page-header";
import { RunPanel, type DocumentSlot } from "@/components/run-panel";
import {
  ContextFields,
  SourceTypeField,
  useSupportedDocumentTypes,
} from "@/components/configuration-fields";
import {
  ConfigField,
  ConfigSelect,
  ConfigurationShell,
} from "@/components/ui/config-field";
import { SectionHeading } from "@/components/ui/section-heading";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ExpertCoverageStrip } from "@/components/expert-coverage-strip";
import { ExpertDocumentTrace } from "@/components/expert-document-trace";
import { answersPerDocument } from "@/lib/expert-document-trace";
import {
  fetchExpertGates,
  runExpert,
  type GateReview,
  type GateSpec,
  type QuestionAssessment,
} from "@/lib/api";
import {
  EXPERT_EMPTY_MESSAGE,
  EXPERT_ORDER_NOTE,
  countStates,
  groupedByDiscipline,
  countRequiredInState,
} from "@/lib/expert-priorities";
import {
  expertResultFilename,
  packExpertResult,
  runLabel,
  runScope,
  unpackExpertResult,
  readResultIdentity,
} from "@/lib/result-file";
import { useExpertSession } from "@/lib/session";
import { isContextComplete, useHeaderStore } from "@/lib/store";
import { displayLabel } from "@/lib/display-label";
import { CONTEXT_ACCEPT, CONTEXT_FORMAT_HINT } from "@/lib/document-formats";
import { EYEBROW } from "@/lib/typography";
import { cn } from "@/lib/utils";
import { Reading } from "@/components/ui/evidence-text";

const STEPS = [
  { key: "resolve", label: "Resolving the question bank" },
  { key: "parse", label: "Parsing documents" },
  { key: "assess", label: "Triaging questions" },
];

type DocumentChoice = { key: string; sourceType: string };
/**
 * One transient context item: a file, and the name an answer is attributed to.
 *
 * The label is the reader's, not the filename. It is what appears beside an answer read
 * from this source, and `AIV_CMC_final_v3` is not an attribution — so the filename is
 * only a starting point, editable before the run.
 */
type ContextRow = { key: string; label: string; file: File | null };

const INITIAL_CHOICES: DocumentChoice[] = [{ key: "d1", sourceType: "" }];

export default function ExpertPage() {
  const session = useExpertSession();
  const header = useHeaderStore((state) => state.header);
  const [gates, setGates] = useState<GateSpec[]>([]);
  const [gate, setGate] = useState("");
  const [choices, setChoices] = useState<DocumentChoice[]>(INITIAL_CHOICES);
  const [contextRows, setContextRows] = useState<ContextRow[]>([]);
  const [showSetup, setShowSetup] = useState(!session.result);
  const importRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (session.result) setShowSetup(false);
  }, [session.result]);

  useEffect(() => {
    if (!header.org || !header.intervention_class) {
      setGates([]);
      return;
    }
    let live = true;
    // Surfaced rather than swallowed: without the declared gates there is nothing
    // to select, so Run would gate with no way for the user to learn why.
    fetchExpertGates(header.org, header.intervention_class)
      .then((loaded) => live && setGates(loaded))
      .catch(
        (error: Error) =>
          live &&
          session.setError(
            `Could not load the gates Expert asks about: ${error.message}`,
          ),
      );
    return () => {
      live = false;
    };
  }, [header.intervention_class, header.org, session.setError]);

  // A type chosen under one context does not exist under another, so changing
  // either clears the rows rather than leaving a stale selection.
  useEffect(() => {
    setChoices(INITIAL_CHOICES);
  }, [header.org, header.intervention_class]);

  const chosen = choices.map((choice) => choice.sourceType).filter(Boolean);
  const slots: readonly DocumentSlot[] = chosen.map((sourceType) => ({
    id: sourceType,
    label: displayLabel(sourceType),
  }));
  const contextReady = isContextComplete(header);
  const configured = contextReady && Boolean(gate) && chosen.length > 0;
  // A row with a file but no name is dropped rather than sent: the label is what an
  // answer is attributed to, so an unnamed source could be attributed to nothing.
  const contextItems = contextRows.flatMap((row) =>
    row.file && row.label.trim()
      ? [{ label: row.label.trim(), file: row.file }]
      : [],
  );

  async function handleRun(files: Record<string, File>) {
    if (!configured || !contextReady) return;
    session.setBusy(true);
    session.setError(null);
    session.setStage(null);
    session.setProgress(null);
    try {
      const result = await runExpert(
        // Read from the slots this page declared, never from every file the panel is
        // holding: a type the user switched away from may still have one.
        chosen.map((sourceType) => ({ file: files[sourceType], sourceType })),
        {
          gate,
          org: header.org,
          intervention_class: header.intervention_class,
          indication: header.indication,
        },
        contextItems,
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
      session.addResult(unpackExpertResult(raw), readResultIdentity(raw));
    } catch (error) {
      session.setError(`Could not import result: ${(error as Error).message}`);
    }
  }

  return (
    <>
      <PageHeader
        title="Expert"
        description="The iTPP, cTPP, and IPDP against the stage-gate criteria: what is still unresolved, and which reviewer it goes to."
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
            hint={runHint(contextReady, gate, chosen.length)}
            runLabel="Run triage"
            busyLabel="Triaging"
            configuration={
              <ConfigurationShell>
                <ContextFields />
                <div className="mt-4">
                  <ConfigField
                    label="Stage gate"
                    disabled={!header.org}
                    note={
                      /*
                        An empty list is explained rather than left empty. It happened
                        once for a different reason — a renamed field emptied this picker
                        with no error anywhere — and a reader cannot tell "no bank for
                        this modality" from "something is broken" without being told.
                      */
                      header.org &&
                      header.intervention_class &&
                      gates.length === 0 ? (
                        <p className="mt-1.5 text-[11px] leading-relaxed text-muted-foreground">
                          No stage-gate bank covers{" "}
                          {displayLabel(header.intervention_class)}. The banks
                          are written for small-molecule drug programs — they
                          ask about synthetic routes, salt forms and BCS class —
                          so a review here would ask questions this modality has
                          no answer to.
                        </p>
                      ) : undefined
                    }
                  >
                    <ConfigSelect
                      value={gate || undefined}
                      // Already in development order from the service, which owns
                      // the ordinal. Nothing sorts them here.
                      options={gates.map((item) => ({
                        value: item.id,
                        label: item.label,
                      }))}
                      disabled={!header.org || gates.length === 0}
                      onChange={setGate}
                    />
                  </ConfigField>
                </div>
                <DocumentChooser
                  choices={choices}
                  disabled={!contextReady}
                  onChange={setChoices}
                />
                <ContextChooser rows={contextRows} onChange={setContextRows} />
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
          <ReviewView
            result={session.result}
            onNewAnalysis={() => setShowSetup(true)}
          />
        )}
      </div>
    </>
  );
}

/** Names the one missing thing, rather than reporting that something is missing. */
function runHint(
  contextReady: boolean,
  gate: string,
  documentCount: number,
): string | undefined {
  if (!contextReady) return "Complete the configuration to run.";
  if (!gate) return "Choose the stage gate this review is preparing for.";
  if (documentCount === 0) return "Add at least one document to read.";
  return undefined;
}

/**
 * Which documents this run reads.
 *
 * Each row offers only the types no other row has taken, so two documents of one
 * type — which the service refuses — cannot be selected in the first place. One
 * document is a valid run: Expert checks coverage rather than comparing, so it has
 * no minimum pair. Fewer documents move questions to "needs a document"; they never
 * change the denominator.
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
  const { types } = useSupportedDocumentTypes();
  const available = new Set((types ?? []).map((item) => item.source_type)).size;
  const taken = choices.map((choice) => choice.sourceType).filter(Boolean);
  const canAdd = !disabled && choices.length < available;

  return (
    <div className="mt-4">
      <div className="flex flex-col gap-3">
        {choices.map((choice, index) => (
          <div key={choice.key} className="flex items-end gap-1.5">
            <div className="min-w-0 flex-1">
              <SourceTypeField
                label={`Document ${index + 1}`}
                value={choice.sourceType || undefined}
                exclude={taken}
                // Once, under the first row: the note is about what the field does,
                // not about one document, so repeating it per row is noise.
                hint={index === 0}
                onChange={(value) =>
                  onChange(
                    choices.map((item, position) =>
                      position === index
                        ? { ...item, sourceType: value }
                        : item,
                    ),
                  )
                }
              />
            </div>
            <button
              type="button"
              aria-label={`Remove document ${index + 1}`}
              disabled={disabled || choices.length <= 1}
              onClick={() =>
                onChange(choices.filter((_, position) => position !== index))
              }
              className="mb-0.5 shrink-0 rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground disabled:pointer-events-none disabled:opacity-30 motion-reduce:transition-none"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        ))}
      </div>
      <button
        type="button"
        disabled={!canAdd}
        onClick={() =>
          onChange([...choices, { key: `d${Date.now()}`, sourceType: "" }])
        }
        className="mt-2.5 inline-flex items-center gap-1 text-xs font-medium text-primary transition-colors hover:text-primary/80 disabled:pointer-events-none disabled:opacity-40 motion-reduce:transition-none"
      >
        <Plus className="h-3.5 w-3.5" />
        Add document
      </button>
    </div>
  );
}

/**
 * Material the gate asks about that no TPP or plan carries.
 *
 * Attached rather than pasted: nobody has the text of a CMC report to hand, and everybody
 * has the file. The service reads it into prose and discards it, so this path stays
 * separate from the canonical one in every way that matters — the text is never chunked,
 * never cited, and never stored, so an answer from it names this label and carries no
 * passage. Which is why the label is required and why it is the reader's own words rather
 * than the filename: it is the whole of the attribution.
 *
 * Its accepted formats are wider than an upload's for that same reason. An upload becomes
 * citable blocks and needs declared structure; this becomes a paragraph in a prompt.
 */
function ContextChooser({
  rows,
  onChange,
}: {
  rows: ContextRow[];
  onChange: (next: ContextRow[]) => void;
}) {
  function update(index: number, patch: Partial<ContextRow>) {
    onChange(
      rows.map((item, position) =>
        position === index ? { ...item, ...patch } : item,
      ),
    );
  }

  return (
    <div className="mt-5 border-t border-border pt-4">
      <p className="text-xs font-medium text-foreground">Additional context</p>
      <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">
        Attach material the documents do not contain: a CMC summary, meeting
        minutes. Its text is read for this run only and never saved, so an
        answer from it names the source and cites no passage.{" "}
        {CONTEXT_FORMAT_HINT}.
      </p>
      <div className="mt-3 flex flex-col gap-3">
        {rows.map((row, index) => (
          <div key={row.key} className="rounded-md border border-border p-2.5">
            <div className="flex items-center gap-1.5">
              <input
                value={row.label}
                placeholder="Name this source, e.g. CMC Development Report"
                onChange={(event) =>
                  update(index, { label: event.target.value })
                }
                className="h-8 min-w-0 flex-1 rounded-md border border-input bg-card px-2.5 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-ring/20"
              />
              <button
                type="button"
                aria-label={`Remove context item ${index + 1}`}
                onClick={() =>
                  onChange(rows.filter((_, position) => position !== index))
                }
                className="shrink-0 rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground motion-reduce:transition-none"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
            <label className="mt-2 flex min-h-9 cursor-pointer items-center gap-2 rounded-md border border-dashed border-input px-2.5 py-1.5 text-xs text-muted-foreground transition-colors hover:border-foreground/25 hover:text-foreground motion-reduce:transition-none">
              <Paperclip aria-hidden="true" className="h-3.5 w-3.5 shrink-0" />
              <span className="min-w-0 flex-1 truncate">
                {row.file ? row.file.name : "Choose a file"}
              </span>
              <input
                type="file"
                accept={CONTEXT_ACCEPT}
                className="hidden"
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (!file) return;
                  // The filename starts the label off, because most of the time it is
                  // close enough to edit; an empty field is one more thing to type.
                  update(index, {
                    file,
                    label:
                      row.label.trim() || file.name.replace(/\.[^.]+$/, ""),
                  });
                  event.target.value = "";
                }}
              />
            </label>
          </div>
        ))}
      </div>
      <button
        type="button"
        onClick={() =>
          onChange([...rows, { key: `c${Date.now()}`, label: "", file: null }])
        }
        className="mt-2.5 inline-flex items-center gap-1 text-xs font-medium text-primary transition-colors hover:text-primary/80 motion-reduce:transition-none"
      >
        <Plus className="h-3.5 w-3.5" />
        Add context
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Result
// ---------------------------------------------------------------------------

function ReviewView({
  result,
  onNewAnalysis,
}: {
  result: { review: GateReview };
  onNewAnalysis: () => void;
}) {
  const { results, selectedId, selectResult, removeResult } =
    useExpertSession();
  const review = result.review;
  const counts = useMemo(() => countStates(review), [review]);
  const answersByDocument = useMemo(() => answersPerDocument(review), [review]);

  // Same handoff Inspector uses: a citation anywhere opens that passage in the trace,
  // so the two views are one navigation rather than two places to look.
  const [resultTab, setResultTab] = useState("questions");
  const revealTrace = useCallback(() => setResultTab("trace"), []);
  const {
    focus: traceFocus,
    open: openBlockInTrace,
    consume: consumeTraceFocus,
  } = useTraceFocus(revealTrace);

  // The gate is in the title via `runLabel`, so it is not repeated here.

  return (
    <ResultLayout
      title={runLabel(result, "expert")}
      subtitle={runScope(result, "expert")}
      // Run-wide, so it holds on the Documents tab too. It was inside the Questions tab.
      metrics={
        <CountRow
          counts={counts}
          requiredOpen={
            countRequiredInState(review, "not_found") +
            countRequiredInState(review, "partly_answered")
          }
        />
      }
      // `answered` and `gaps` show at zero because a model decides those two, so a zero
      // there says the check ran. The rest come from config and the uploads.
      metricsNote="Every question in the bank by state. Answered, partly answered and not found appear even at zero, because a zero there says the check ran and found nothing."
      tabValue={resultTab}

      onTabChange={setResultTab}
      tabs={
        <>
          {/*
            Questions first, unlike Inspector, and for the reason Inspector opens
            on its document: a tool opens on what it is about. Inspector is about
            one document; Expert is about the gate's questions, and the documents
            are what it read to answer them.
          */}
          <TabsTrigger value="questions">Questions</TabsTrigger>
          <TabsTrigger value="trace">Documents</TabsTrigger>
        </>
      }
      actions={
        <>
          <RunHistory
            runs={results}
            selectedId={selectedId}
            onSelect={selectResult}
            onRemove={removeResult}
            label={(value) => runLabel(value, "expert")}
          />
          <FinalResultActions
            onNewAnalysis={onNewAnalysis}
            download={{
              filename: expertResultFilename(result),
              data: packExpertResult(result),
            }}
          />
        </>
      }
    >
      <DocumentSourceProvider
        blocks={review.blocks}
        onOpenInTrace={openBlockInTrace}
      >
        <TabsContent value="questions" className="m-0">
          {/* The view's nav: its name, and what explains it. */}
          <ResultToolbar>
            <p className="min-w-0 flex-1 text-xs font-medium text-foreground">
              Questions
            </p>
            {/* No count: nothing filters here, and the figure row above already
                  states every question state and what they sum to. */}
            <ResultToolbarEnd>
              <ExpertSignalHelp />
            </ResultToolbarEnd>
          </ResultToolbar>
          <div className="flex flex-col gap-6 px-5 py-5 sm:px-6">
            <ExpertCoverageStrip
              review={review}
              onSelect={(question) => {
                // A cell opens the passage behind its answer when there is one;
                // otherwise there is nothing to open and the cell stays inert.
                const blockId = question.cited_block_ids[0];
                // No annotation: a coverage cell names a question, not one result on
                // the passage, so the trace opens showing every layer the block carries.
                if (blockId) openBlockInTrace({ blockId });
              }}
            />

            {/*
                Expert does not use the shared `PriorityPanel`, and that is a deliberate
                exception rather than drift. For Inspector and Scout the panel digests
                items scattered across dozens of units into one opening list. Expert's
                unanswered questions are already one flat list, so the panel showed the
                same items a second time — and `PriorityItem` cannot carry a 40-60 word
                question, so it showed Expert's comment with the question it was about
                missing. The panel below carries both.
              */}
            {/*
                Partials first. They are the only state with a specific ask attached —
                the material got part of the way and `missing` names the rest — so this
                is the panel a PPL acts on. Answered needs nothing, and not found is
                either a reviewer's question or a larger conversation.
              */}
            <StatePanel
              title="Partly answered"
              description="Some of the question is answered and some is not. Each says what is still not stated."
              state="partly_answered"
              review={review}
              defaultOpen
              orderNote={EXPERT_ORDER_NOTE}
            />

            <StatePanel
              title="Not found in the documents"
              description="Nothing in the supplied material addresses these. Each shows the discipline that owns it."
              state="not_found"
              review={review}
              emptyMessage={EXPERT_EMPTY_MESSAGE}
              orderNote={EXPERT_ORDER_NOTE}
            />

            <StatePanel
              title="Answered"
              description="What the supplied material already answers."
              state="answered"
              review={review}
              trailing={`${counts.cited} cited to a passage · ${counts.fromContext} from supplied context`}
            />

            <BankSource source={review.bank_source} />
          </div>
        </TabsContent>

        <TabsContent value="trace" className="m-0">
          <div className="border-b border-border px-5 py-3 sm:px-6">
            <p className="text-[11px] leading-relaxed text-muted-foreground">
              Which passages carried an answer, whole or partial, and what they
              answered. The inverse of the questions view. Only answers read
              from a document appear here: an answer from attached context has
              no passage, and an unanswered question has nothing to mark.
            </p>
            {/*
                Not addable, and it says so. One question can cite passages from two
                documents, so these overlap and their sum exceeds the answered count on
                the questions view. Stating it beats letting a reader add them.
              */}
            <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">
              {answersByDocument
                .map(
                  (entry) =>
                    `${displayLabel(entry.sourceType)} answered ${entry.count}`,
                )
                .join(" · ")}
              . A question citing both documents is counted in both, so these do
              not sum to the answered total.
            </p>
          </div>
          <ExpertDocumentTrace
            review={review}
            focus={traceFocus}
            onFocusConsumed={consumeTraceFocus}
          />
        </TabsContent>
      </DocumentSourceProvider>
    </ResultLayout>
  );
}

/**
 * What question bank this triage came from.
 *
 * Read off the result rather than from the config, so a downloaded review states its
 * own authority: the bank will be revised, and only this line says which version
 * produced these questions. Rendered small and last — it is provenance, not a
 * finding — but present, because a reviewer asked to act on 80 questions is entitled
 * to know where they came from.
 */
function BankSource({ source }: { source: string }) {
  if (!source.trim()) return null;
  const [prose, link] = splitTrailingUrl(source);
  return (
    <p className="text-[11px] leading-relaxed text-muted-foreground">
      Questions from {prose}
      {link && (
        <>
          {" "}
          <a
            href={link}
            target="_blank"
            rel="noreferrer"
            className="underline hover:text-foreground"
          >
            Open the source
          </a>
        </>
      )}
    </p>
  );
}

/**
 * Separate a trailing URL from the prose that precedes it.
 *
 * The config states provenance as one sentence ending in a link, because a config is
 * prose and splitting it into fields there would invite a second answer about the
 * same source. Splitting it here is presentation.
 */
function splitTrailingUrl(source: string): [string, string | null] {
  const match = source.match(/^(.*?)\s*(?:—\s*)?(https?:\/\/\S+)$/s);
  if (!match) return [source.trim(), null];
  return [match[1].replace(/[\s—–-]+$/, "").trim(), match[2]];
}

/**
 * The counts, in one row that sums to the total.
 *
 * No combined coverage figure. One number blending "the document says it" with
 * "an SME will answer it" would tell a governance committee something untrue,
 * which is the same reason Scout refuses to blend its axes into a score.
 */
function CountRow({
  counts,
  requiredOpen,
}: {
  counts: ReturnType<typeof countStates>;
  /** Questions this gate requires answered now that nothing supplied answers. */
  requiredOpen: number;
}) {
  // `answered` and `gaps` are always shown, even at zero, because those two are the
  // only states a model decides: a zero there says the check ran and found nothing,
  // which is information. Hiding it made a run that assessed almost nothing look
  // like a run with no such concept — the figures still summed to the total, so
  // nothing seemed wrong. The other three come from config and the uploads, so a
  // zero in them genuinely has nothing to report.
  const cells = [
    { label: "answered", value: counts.answered, always: true },
    { label: "partly answered", value: counts.partlyAnswered, always: true },
    { label: "not found", value: counts.notFound, always: true },
    { label: "not applicable", value: counts.notApplicable, always: false },
  ].filter((cell) => cell.always || cell.value > 0);

  const assessed = counts.answered + counts.partlyAnswered + counts.notFound;
  return (
    <div>
      {/*
        No `SignalHelp` here. It moved to the tab row above, which is the control row
        Inspector and Scout put theirs on; leaving a copy beside the counts would put
        the same affordance on screen twice.
      */}
      <dl className="flex flex-wrap items-baseline gap-x-5 gap-y-1.5">
        {cells.map((cell) => (
          <div key={cell.label} className="flex items-baseline gap-1.5">
            <dd
              className={`text-sm font-semibold tabular-nums ${cell.value > 0 ? "text-foreground" : "text-muted-foreground"}`}
            >
              {cell.value}
            </dd>
            <dt className="text-xs text-muted-foreground">{cell.label}</dt>
          </div>
        ))}
      </dl>
      {/*
        Said as a sentence rather than added to the row above, because it is not a sixth
        state — it is a cut across two of them, and standing beside the states it would
        break the rule that the row sums to the total. It is the one figure worth quoting
        in a review: the bank says which questions this gate requires, so an unanswered
        required question is what holds the gate, and an unanswered anticipatory one is
        early warning about the next.
      */}
      {requiredOpen > 0 && (
        <p className="mt-2 text-xs text-foreground">
          {/* The whole sentence is the label, not a clause inside it: SignalLabel
              puts its help icon after its children, so wrapping the middle left
              the icon standing between "are" and "still unanswered". */}
          <ExpertSignalLabel topic="requirement">
            <span>
              <span className="font-semibold tabular-nums">{requiredOpen}</span>{" "}
              {requiredOpen === 1
                ? "question this gate requires is still unanswered."
                : "questions this gate requires are still unanswered."}
            </span>
          </ExpertSignalLabel>
        </p>
      )}
      <p className="mt-2 border-t border-border pt-2 text-[11px] leading-relaxed text-muted-foreground">
        {counts.total} questions in this gate. Every one is counted, so the
        figures above sum to that.{" "}
        {assessed === 0
          ? "None was read: every question in this bank states that it applies to another intervention class."
          : `${assessed} ${assessed === 1 ? "was" : "were"} read against everything supplied. Any remainder is a question whose own text states it applies to another intervention class.`}
      </p>
    </div>
  );
}

/**
 * Which upload would make the unassessable questions assessable.
 *
 * Absent entirely when nothing is missing, so a complete run gains no chrome.
 */
/**
 * One state's questions, grouped by the discipline that owns them.
 *
 * Grouped rather than a flat list: the discipline was printed on every row, so ten
 * consecutive questions each said "CMC" and the eye had to find where one discipline
 * ended. A subheading says it once and carries its own count, which also removed the
 * run-on string of eight labelled counts that used to sit beside the panel heading and
 * overflow its row.
 *
 * The count sits beside the title as `<title> <count>`, the grammar `PriorityPanel`
 * uses, so a reader is not asked to learn two ways of writing the same thing.
 */
function StatePanel({
  title,
  description,
  state,
  review,
  trailing,
  defaultOpen = false,
  emptyMessage,
  orderNote,
}: {
  title: string;
  description: string;
  state: QuestionAssessment["state"];
  review: GateReview;
  trailing?: string;
  defaultOpen?: boolean;
  /** Shown in place of the list when nothing is in this state. */
  emptyMessage?: string;
  /** How the order was decided. Stated because nothing here re-ranks. */
  orderNote?: string;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const groups = useMemo(
    () => groupedByDiscipline(review, state),
    [review, state],
  );
  const total = groups.reduce((sum, group) => sum + group.questions.length, 0);
  // A panel with an empty message still renders at zero, because "nothing unanswered"
  // is a result. One without stays absent, because an empty state is not news.
  if (total === 0 && !emptyMessage) return null;

  return (
    <section className="rounded-lg border border-border">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
        className="flex w-full items-start gap-3 px-4 py-3.5 text-left"
      >
        <span className="min-w-0 flex-1">
          <SectionHeading
            title={
              <>
                {title}{" "}
                <span className="font-normal tabular-nums text-muted-foreground">
                  {total}
                </span>
              </>
            }
            description={description}
            trailing={trailing}
          />
        </span>
        <ChevronDown
          className={`mt-0.5 h-4 w-4 shrink-0 text-muted-foreground transition-transform duration-base motion-reduce:transition-none ${open ? "" : "-rotate-90"}`}
        />
      </button>
      {open && (
        <>
          {total === 0 ? (
            <p className="border-t border-border px-4 py-3 text-xs leading-relaxed text-muted-foreground">
              {emptyMessage}
            </p>
          ) : (
            /*
              One collapsed card per discipline, which is what Inspector does with its
              rubric sections. A plain heading was worse than no grouping: with nine
              long questions under it the heading scrolled away immediately and there
              was nothing to say which discipline you were reading until the next one,
              seventy rows later.

              Not tabs. This already sits inside the Questions tab, so a second tab
              level would put two of them on one screen, and eight tabs labelled
              "Preclinical Pharmacology / Toxicology / PK" do not fit a row anyway.
            */
            <div className="flex flex-col gap-2 border-t border-border px-4 py-4">
              {groups.map((group) => (
                <CollapsibleCard
                  key={group.id}
                  title={group.label}
                  defaultOpen={false}
                  contentClassName="px-0 py-0 sm:px-0"
                  trailing={
                    <span className="text-xs tabular-nums text-muted-foreground">
                      {group.questions.length}
                    </span>
                  }
                >
                  <ul className="divide-y divide-border border-t border-border">
                    {group.questions.map((question) => (
                      <QuestionRow key={question.id} question={question} />
                    ))}
                  </ul>
                </CollapsibleCard>
              ))}
            </div>
          )}
          {orderNote && total > 0 && (
            <p className="border-t border-border px-4 py-3 text-[11px] leading-relaxed text-muted-foreground">
              {orderNote}
            </p>
          )}
        </>
      )}
    </section>
  );
}

/**
 * One question.
 *
 * Clamped to two lines, expanding to the whole question. Deliberately not a short
 * form stored beside the text: hand-written summaries would drift from the question
 * they summarise, and truncating in code would be a transformation of authored
 * content. Clamping is rendering, so the text stays the text.
 */
function QuestionRow({ question }: { question: QuestionAssessment }) {
  const [open, setOpen] = useState(false);
  return (
    <li className="px-4 py-3">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
        className="w-full text-left"
      >
        <span className="flex items-baseline justify-end gap-3">
          <span className="flex shrink-0 items-center gap-2">
            {/*
              The badge keeps its own border; the explainer sits outside it, so the
              pill reads as one token rather than as a bordered box containing a
              question mark. Every other label in this result is explainable, and
              this was the only one a reader could not ask about.
            */}
            {question.requirement === "required" && (
              <ExpertSignalLabel topic="requirement">
                <span
                  className={cn(
                    "rounded border border-border px-1.5 py-px",
                    EYEBROW,
                  )}
                >
                  Required
                </span>
              </ExpertSignalLabel>
            )}
            <span className="font-mono text-[11px] tabular-nums text-muted-foreground">
              {question.id}
            </span>
          </span>
        </span>
        <p
          className={`mt-1 text-xs leading-relaxed text-muted-foreground ${open ? "" : "line-clamp-2"}`}
        >
          {question.text}
        </p>
      </button>
      {/* The model's answer, so muted and marked - it was at full contrast, which is
          the treatment for the tool's own words and the document's values. */}
      {question.statement && (
        <Reading size="body" className="mt-2">{question.statement}</Reading>
      )}
      {/*
        The ask, given its own line rather than left inside the statement. On a partial
        this is the sentence that goes back to the grantee, and burying it in prose is
        why it was required as a field in the first place.
      */}
      {question.missing && (
        <Reading size="body" className="mt-1.5">
          <span className="font-medium">Still not stated: </span>
          {question.missing}
        </Reading>
      )}
      {open && <Provenance question={question} />}
    </li>
  );
}

/**
 * Where an answer came from.
 *
 * The same field in the same place for both sources, so a context answer reads as a
 * property rather than a warning: it was addressed, it just cannot be checked from
 * the file. The text behind it was never stored, so this label is the whole record.
 */
function Provenance({ question }: { question: QuestionAssessment }) {
  // Nothing to show for a question no answer was found for. There used to be a line
  // here naming the document such an answer usually lives in, which no source states.
  if (question.state !== "answered") return null;
  if (question.source === "context") {
    return (
      <p className="mt-2 text-[11px] text-muted-foreground">
        Source: {question.context_label} · no passage reference
      </p>
    );
  }
  return (
    <div className="mt-2">
      <p className="text-[11px] text-muted-foreground">Source</p>
      <DocumentSourceTrace blockIds={question.cited_block_ids} />
    </div>
  );
}
