"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, ChevronDown, Plus, X } from "lucide-react";
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
  suggestedDocuments,
} from "@/lib/expert-priorities";
import {
  expertResultFilename,
  packExpertResult,
  unpackExpertResult,
  readResultIdentity,
} from "@/lib/result-file";
import { useExpertSession } from "@/lib/session";
import { isContextComplete, useHeaderStore } from "@/lib/store";
import { displayLabel } from "@/lib/display-label";

const STEPS = [
  { key: "resolve", label: "Resolving the question bank" },
  { key: "parse", label: "Parsing documents" },
  { key: "assess", label: "Triaging questions" },
];

type DocumentChoice = { key: string; sourceType: string };
type ContextRow = { key: string; label: string; text: string };

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
    if (!header.org) {
      setGates([]);
      return;
    }
    let live = true;
    // Surfaced rather than swallowed: without the declared gates there is nothing
    // to select, so Run would gate with no way for the user to learn why.
    fetchExpertGates(header.org)
      .then((loaded) => live && setGates(loaded))
      .catch(
        (error: Error) =>
          live &&
          session.setError(`Could not load the gates Expert asks about: ${error.message}`),
      );
    return () => {
      live = false;
    };
  }, [header.org, session.setError]);

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
  const contextItems = contextRows
    .map((row) => ({ label: row.label.trim(), text: row.text.trim() }))
    .filter((row) => row.label && row.text);

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
                  <ConfigField label="Stage gate" disabled={!header.org}>
                    <ConfigSelect
                      value={gate || undefined}
                      // Already in development order from the service, which owns
                      // the ordinal. Nothing sorts them here.
                      options={gates.map((item) => ({
                        value: item.id,
                        label: item.label,
                      }))}
                      disabled={!header.org}
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
                      position === index ? { ...item, sourceType: value } : item,
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
 * Pasted rather than uploaded, and deliberately so: a file would need parsing,
 * which would drag in the format rules canonical documents follow. This text goes
 * into the request and is never stored, so an answer from it names this label and
 * carries no passage — which is why the label is required.
 */
function ContextChooser({
  rows,
  onChange,
}: {
  rows: ContextRow[];
  onChange: (next: ContextRow[]) => void;
}) {
  return (
    <div className="mt-5 border-t border-border pt-4">
      <p className="text-xs font-medium text-foreground">Additional context</p>
      <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">
        Paste material the documents do not contain — a CMC summary, meeting
        minutes. It is used for this run only and never saved, so an answer read
        from it names the source and cites no passage.
      </p>
      <div className="mt-3 flex flex-col gap-3">
        {rows.map((row, index) => (
          <div key={row.key} className="rounded-md border border-border p-2.5">
            <div className="flex items-center gap-1.5">
              <input
                value={row.label}
                placeholder="Name this source, e.g. CMC Development Report"
                onChange={(event) =>
                  onChange(
                    rows.map((item, position) =>
                      position === index
                        ? { ...item, label: event.target.value }
                        : item,
                    ),
                  )
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
            <textarea
              value={row.text}
              rows={3}
              placeholder="Paste the text"
              onChange={(event) =>
                onChange(
                  rows.map((item, position) =>
                    position === index ? { ...item, text: event.target.value } : item,
                  ),
                )
              }
              className="mt-2 w-full resize-y rounded-md border border-input bg-card px-2.5 py-2 text-xs leading-relaxed text-foreground focus:outline-none focus:ring-2 focus:ring-ring/20"
            />
          </div>
        ))}
      </div>
      <button
        type="button"
        onClick={() =>
          onChange([...rows, { key: `c${Date.now()}`, label: "", text: "" }])
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
  const review = result.review;
  const counts = useMemo(() => countStates(review), [review]);
  const suggested = useMemo(() => suggestedDocuments(review), [review]);
  const answersByDocument = useMemo(() => answersPerDocument(review), [review]);

  // Same handoff Inspector uses: a citation anywhere opens that passage in the trace,
  // so the two views are one navigation rather than two places to look.
  const [resultTab, setResultTab] = useState("questions");
  const [traceFocusBlockId, setTraceFocusBlockId] = useState<string | null>(null);
  const openBlockInTrace = useCallback((blockId: string) => {
    setTraceFocusBlockId(blockId);
    setResultTab("trace");
  }, []);
  const consumeTraceFocus = useCallback((blockId: string) => {
    setTraceFocusBlockId((current) => (current === blockId ? null : current));
  }, []);

  const subtitle = [
    review.gate_label,
    displayLabel(review.intervention_class),
    review.documents.map((document) => displayLabel(document.source_type)).join(", "),
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <CollapsibleCard
      title={`${review.gate_label} review`}
      subtitle={subtitle}
      defaultOpen
      contentClassName="px-0 py-0 sm:px-0"
      trailing={
        <FinalResultActions
          onNewAnalysis={onNewAnalysis}
          download={{
            filename: expertResultFilename(result),
            data: packExpertResult(result),
          }}
        />
      }
    >
      <DocumentSourceProvider blocks={review.blocks} onOpenInTrace={openBlockInTrace}>
        <Tabs value={resultTab} onValueChange={setResultTab} className="w-full">
          <div className="flex items-center justify-between gap-3 border-b border-border px-5 pt-2 sm:px-6">
            <TabsList className="justify-start border-b-0">
              {/*
                Questions first, unlike Inspector, and for the reason Inspector opens
                on its document: a tool opens on what it is about. Inspector is about
                one document; Expert is about the gate's questions, and the documents
                are what it read to answer them.
              */}
              <TabsTrigger value="questions">Questions</TabsTrigger>
              <TabsTrigger value="trace">Documents</TabsTrigger>
            </TabsList>
            <ExpertSignalHelp />
          </div>

          <TabsContent value="questions" className="m-0">
            <div className="flex flex-col gap-6 px-5 py-5 sm:px-6">
              <CountRow counts={counts} />
              <ExpertCoverageStrip
                review={review}
                onSelect={(question) => {
                  // A cell opens the passage behind its answer when there is one;
                  // otherwise there is nothing to open and the cell stays inert.
                  const blockId = question.cited_block_ids[0];
                  if (blockId) openBlockInTrace(blockId);
                }}
              />
              {suggested.length > 0 && <SuggestedDocuments suggested={suggested} />}

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
                Which passages carried an answer — whole or partial — and what they
                answered. The inverse of the questions view. Only answers read from a
                document appear here: an answer from pasted context has no passage, and
                an unanswered question has nothing to mark.
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
                . A question citing both documents is counted in both, so these do not
                sum to the answered total.
              </p>
            </div>
            <ExpertDocumentTrace
              review={review}
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
function CountRow({ counts }: { counts: ReturnType<typeof countStates> }) {
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
      <p className="mt-2 border-t border-border pt-2 text-[11px] leading-relaxed text-muted-foreground">
        {counts.total} questions in this gate. Every one is counted, so the figures
        above sum to that.{" "}
        {assessed === 0
          ? "None was read: the question bank states that every question here applies to another intervention class."
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
 * Documents worth uploading next.
 *
 * A suggestion, and worded as one. Every question counted here *was* assessed against
 * what was supplied and was not answered there — the bank's hint about where such an
 * answer usually lives is a judgment, not something the source question bank states,
 * so this cannot promise the question would have been answered. Amber because it is
 * the most actionable thing on the page, not because anything failed.
 */
function SuggestedDocuments({
  suggested,
}: {
  suggested: { sourceType: string; count: number }[];
}) {
  return (
    <div
      role="status"
      className="flex items-start gap-2.5 rounded-lg border border-amber-300/60 bg-amber-50/60 px-3.5 py-3 text-xs text-amber-950 dark:border-amber-400/30 dark:bg-amber-400/[0.06] dark:text-amber-200"
    >
      <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
      <div className="min-w-0">
        <p className="font-medium">Another document may answer some of these</p>
        <ul className="mt-1 space-y-0.5 leading-relaxed opacity-80">
          {suggested.map((entry) => (
            <li key={entry.sourceType}>
              {entry.count} unanswered question{entry.count === 1 ? " is" : "s are"}{" "}
              usually answered in {displayLabel(entry.sourceType)}, which was not
              uploaded.
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

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
  const groups = useMemo(() => groupedByDiscipline(review, state), [review, state]);
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
            {question.pq && (
              <ExpertSignalLabel topic="pq">
                <span className="rounded border border-border px-1.5 py-px text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                  PQ
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
      {question.statement && (
        <p className="mt-2 text-sm leading-6 text-foreground">{question.statement}</p>
      )}
      {/*
        The ask, given its own line rather than left inside the statement. On a partial
        this is the sentence that goes back to the grantee, and burying it in prose is
        why it was required as a field in the first place.
      */}
      {question.missing && (
        <p className="mt-1.5 text-sm leading-6 text-foreground">
          <span className="text-muted-foreground">Still not stated: </span>
          {question.missing}
        </p>
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
  if (question.state !== "answered") {
    if (question.likely_in.length === 0) return null;
    // "Usually", because this is the bank's hint rather than something the source
    // question bank states. It says where to look; it does not claim the answer is
    // there, and it played no part in this question's state.
    return (
      <p className="mt-2 text-[11px] text-muted-foreground">
        Usually answered in{" "}
        {question.likely_in.map((type) => displayLabel(type)).join(" or ")}
      </p>
    );
  }
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
