"use client";

import { ResultLayout } from "@/components/ui/result-layout";
import { ResultSearch } from "@/components/ui/result-search";
import { matchesQuery, normalizeQuery } from "@/lib/result-search";
import { MetricsRow } from "@/components/ui/metrics-row";
import { Attributed } from "@/components/ui/attributed";
import { DisclosureRow } from "@/components/ui/disclosure-row";
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
import { ScreenerSignalHelp } from "@/components/screener-signal-help";
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
import { ScreenerCoverageStrip } from "@/components/screener-coverage-strip";
import { ScreenerDocumentTrace } from "@/components/screener-document-trace";
import {
  fetchScreenerGates,
  runScreener,
  type GateReview,
  type GateSpec,
  type QuestionAssessment,
  QUESTION_STATE_LABEL,
  QUESTION_STATE_TONE,
  type QuestionState,
} from "@/lib/api";
import {
  SCREENER_EMPTY_MESSAGE,
  SCREENER_ORDER_NOTE,
  countStates,
  groupedByDiscipline,
  countRequiredInState,
} from "@/lib/screener-priorities";
import {
  screenerResultFilename,
  packScreenerResult,
  runLabel,
  runScope,
  unpackScreenerResult,
  readResultIdentity,
} from "@/lib/result-file";
import { useScreenerSession } from "@/lib/session";
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

export default function ScreenerPage() {
  const session = useScreenerSession();
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
    fetchScreenerGates(header.org, header.intervention_class)
      .then((loaded) => live && setGates(loaded))
      .catch(
        (error: Error) =>
          live &&
          session.setError(
            `Could not load the gates Screener asks about: ${error.message}`,
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
      const result = await runScreener(
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
      session.addResult(unpackScreenerResult(raw), readResultIdentity(raw));
    } catch (error) {
      session.setError(`Could not import result: ${(error as Error).message}`);
    }
  }

  return (
    <>
      <PageHeader
        title="Screener"
        description="The iTPP, cTPP, and IPDP against a stage gate’s question bank: what is still unanswered, and which discipline it goes to. Stage gate readiness, not judgement — it reports what the material does not answer, and decides nothing."
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
 * document is a valid run: Screener checks coverage rather than comparing, so it has
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
    useScreenerSession();
  const review = result.review;
  const counts = useMemo(() => countStates(review), [review]);

  // Same handoff Inspector uses: a citation anywhere opens that passage in the trace,
  // so the two views are one navigation rather than two places to look.
  const [resultTab, setResultTab] = useState("questions");
  // One box for the whole tab: a reader searching "shelf life" is asking the gate, not
  // one state of it, so the query filters every panel below rather than each holding its
  // own. The count beside it is over the whole bank, for the same reason.
  const [query, setQuery] = useState("");
  const normalizedQuery = normalizeQuery(query);
  const shownQuestions = useMemo(
    () =>
      review.disciplines.reduce(
        (sum, discipline) =>
          sum
          + discipline.questions.filter((question) =>
              matchesQuery(
                normalizedQuery,
                question.text,
                question.statement,
                question.missing,
              ),
            ).length,
        0,
      ),
    [review, normalizedQuery],
  );
  const revealTrace = useCallback(() => setResultTab("trace"), []);
  const {
    focus: traceFocus,
    open: openBlockInTrace,
    consume: consumeTraceFocus,
  } = useTraceFocus(revealTrace);

  // The gate is in the title via `runLabel`, so it is not repeated here.

  return (
    <ResultLayout
      title={runLabel(result, "screener")}
      subtitle={runScope(result, "screener")}
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
      metricsNote={screenerMetricsNote(counts)}
      tabValue={resultTab}

      onTabChange={setResultTab}
      tabs={
        <>
          {/*
            Questions first, unlike Inspector, and for the reason Inspector opens
            on its document: a tool opens on what it is about. Inspector is about
            one document; Screener is about the gate's questions, and the documents
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
            label={(value) => runLabel(value, "screener")}
          />
          <FinalResultActions
            onNewAnalysis={onNewAnalysis}
            download={{
              filename: screenerResultFilename(result),
              data: packScreenerResult(result),
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
            {/* A search, not the word "Questions". The band led with a label because
                there was nothing else to put in it, and the label repeated the tab
                directly above. A gate bank runs to seventy-odd questions across eight
                collapsed disciplines in three panels, which is the content least
                scannable by eye in the suite. */}
            <ResultSearch
              label="Search questions"
              placeholder="Find a question…"
              value={query}
              onChange={setQuery}
            />
            <ResultToolbarEnd count={{ shown: shownQuestions, total: counts.total }}>
              <ScreenerSignalHelp />
            </ResultToolbarEnd>
          </ResultToolbar>
          <div className="flex flex-col gap-6 px-5 py-5 sm:px-6">
            <ScreenerCoverageStrip
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
                Screener does not use the shared `PriorityPanel`, and that is a deliberate
                exception rather than drift. For Inspector and Scout the panel digests
                items scattered across dozens of units into one opening list. Screener's
                unanswered questions are already one flat list, so the panel showed the
                same items a second time — and `PriorityItem` cannot carry a 40-60 word
                question, so it showed Screener's comment with the question it was about
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
              query={normalizedQuery}
              defaultOpen
              orderNote={SCREENER_ORDER_NOTE}
            />

            <StatePanel
              title="Not found in the documents"
              description="Nothing in the supplied material addresses these. Each shows the discipline that owns it."
              state="not_found"
              review={review}
              query={normalizedQuery}
              emptyMessage={SCREENER_EMPTY_MESSAGE}
              orderNote={SCREENER_ORDER_NOTE}
            />

            <StatePanel
              title="Answered"
              description="What the supplied material already answers."
              state="answered"
              review={review}
              query={normalizedQuery}
              trailing={`${counts.cited} cited to a passage · ${counts.fromContext} from supplied context`}
            />

            <BankSource source={review.bank_source} />
          </div>
        </TabsContent>

        {/*
          The component alone, as in Inspector, Aligner and Scout. A band above it
          restated two things the page already shows: the split between answers cited to
          a passage and answers from attached context, which the Answered row states
          beside its own count, and a per-document tally, which the trace viewer prints
          live beside the document it is showing. The tally also printed both documents
          at once, so it had to end by asking the reader not to add them - a caution that
          only existed because the numbers were there.
        */}
        <TabsContent value="trace" className="m-0">
          <ScreenerDocumentTrace
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
/**
 * What the figures count, said once, above them.
 *
 * The panel's only prose. Two sentences used to sit *under* the counts instead - one
 * restating the total, one explaining what was read against what - which put an
 * explanation of the figures below the figures and made the panel prose, numbers, prose.
 * A caveat about how counts relate is prose about figures, and this is where that goes.
 */
function screenerMetricsNote(counts: ReturnType<typeof countStates>): string {
  const assessed = counts.answered + counts.partlyAnswered + counts.notFound;
  return [
    "Every question in the bank by state, so the row sums to the number of questions this gate asks.",
    "Answered, partly answered and not found appear even at zero, because a zero there says the check ran and found nothing.",
    assessed === 0
      ? "None was read: every question in this bank states that it applies to another intervention class."
      : `${assessed} of them ${assessed === 1 ? "was" : "were"} read against everything supplied; any remainder is a question whose own text states it applies to another intervention class.`,
    "A question is required when the bank states this gate needs it answered now, rather than at a later one.",
  ].join(" ");
}

function CountRow({
  counts,
  requiredOpen,
}: {
  counts: ReturnType<typeof countStates>;
  /** Questions this gate requires answered now that nothing supplied answers. */
  requiredOpen: number;
}) {
  // Every state, including the zeros. `answered`, `partly answered` and `not found`
  // are decided by a model, so a zero there says the check ran and found nothing -
  // which is information. Hiding it made a run that assessed almost nothing look like a
  // run with no such concept. `not applicable` comes from the bank and the uploads, so
  // a zero in it genuinely has nothing to report.
  const shown: { state: QuestionState; count: number }[] = [
    { state: "answered" as const, count: counts.answered },
    { state: "partly_answered" as const, count: counts.partlyAnswered },
    { state: "not_found" as const, count: counts.notFound },
    { state: "not_applicable" as const, count: counts.notApplicable },
  ].filter((cell) => cell.state !== "not_applicable" || cell.count > 0);

  return (
    <MetricsRow
      total={counts.total}
      unit={["question", "questions"]}
      items={shown.map((cell) => ({
        label: QUESTION_STATE_LABEL[cell.state],
        count: cell.count,
        tone: QUESTION_STATE_TONE[cell.state],
      }))}
      // Cuts across the states above rather than being one of them, so it is a fact
      // and not a bucket: standing in the row it would break the sum a reader has just
      // been invited to check. It was two sentences here, one of them explaining how the
      // counts relate - which is prose about the figures, and now sits in the note.
      facts={
        requiredOpen > 0
          ? [
              {
                value: requiredOpen,
                label:
                  requiredOpen === 1
                    ? "question this gate requires, still unanswered"
                    : "questions this gate requires, still unanswered",
              },
            ]
          : []
      }
    />
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
  query,
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
  /**
   * The search narrowing the questions, or empty.
   *
   * Threaded from the toolbar rather than held here, because one box filters every panel
   * on the tab: a reader searching "shelf life" is asking the gate, not one state of it.
   */
  query?: string;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const groups = useMemo(
    () => groupedByDiscipline(review, state, query),
    [review, state, query],
  );
  const total = groups.reduce((sum, group) => sum + group.questions.length, 0);
  // A panel with an empty message still renders at zero, because "nothing unanswered" is
  // a result. One without stays absent, because an empty state is not news.
  //
  // Under a search neither holds: zero here means the query matched nothing in this
  // state, which is the filter working rather than a finding about the gate, and
  // "nothing unanswered" would be a false claim about the run.
  if (total === 0 && (!emptyMessage || query)) return null;

  return (
    // A card, drawn by the component that draws cards. This was a `section` with its own
    // border, its own chevron, its own rotation and its own padding, standing beside
    // `CollapsibleCard` and doing the same job slightly differently - which is how the
    // nesting below happened: a hand-rolled card does not know it is one, so putting
    // cards inside it looked like a fresh decision rather than a repeat.
    <CollapsibleCard
      title={title}
      subtitle={description}
      // The count in the trailing slot, where every other card in the suite puts it,
      // rather than trailing the title inside the heading. It was inside because this
      // card drew its own header and could put anything anywhere.
      trailing={
        <span className="flex shrink-0 items-center gap-3 text-[11px] text-muted-foreground">
          {trailing && <span>{trailing}</span>}
          <span className="tabular-nums">{total}</span>
        </span>
      }
      defaultOpen={defaultOpen}
    >
      {total === 0 ? (
        <p className="text-xs leading-relaxed text-muted-foreground">
          {emptyMessage}
        </p>
      ) : (
        /*
          A group, not a card. One discipline is a labelled subset of this state with a
          count - which is what `DisclosureRow` is, and what Aligner's verdicts and
          Scout's relations already use. It was a `CollapsibleCard`, so a bordered box sat
          inside a bordered box: Inspector had already found that and written down why it
          is wrong, and the comment here cited Inspector's sections as the precedent
          without noticing that those are the outermost container in their tab and these
          are not.

          Still grouped, which was the right call: with nine long questions under a plain
          heading the heading scrolled away immediately and nothing said which discipline
          you were reading until the next one, seventy rows later.
        */
        <div>
          {groups.map((group) => (
            <DisclosureRow
              key={group.id}
              label={group.label}
              count={group.questions.length}
              defaultOpen={Boolean(query)}
            >
              <ul className="divide-y divide-border/60">
                {group.questions.map((question) => (
                  <QuestionRow key={question.id} question={question} />
                ))}
              </ul>
            </DisclosureRow>
          ))}
        </div>
      )}
      {orderNote && total > 0 && (
        // Inset with the content, because the card pads its own. This card used to turn
        // that padding off and re-add it on every child - three cards in the suite, two
        // ways of attaching one style, and the only way to tell which a card used was to
        // read it.
        <p className="mt-3 border-t border-border pt-3 text-[11px] leading-relaxed text-muted-foreground">
          {orderNote}
        </p>
      )}
    </CollapsibleCard>
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
        {/*
          The question and what identifies it on one line, not two. The badge and the ID
          were a right-aligned row of their own above the text, so the two floated apart:
          a label at the far right of an empty line, and the thing it labels beginning
          under the left margin. Same shape as `Attributed` - the subject takes the line
          and what names it sits at the end of it.

          No explainer on the badge. It carried one, on the reasoning that every other
          label in this result is explainable and this was the only one a reader could not
          ask about - true, but the icon was the wrong answer. It repeated identically on
          every required row, and it could not teach the thing a reader needs: `required`
          only means something against `anticipatory`, and an anticipatory question has no
          badge for an icon to sit on. "How to read" is on the toolbar and lists every
          topic beside the ones it contrasts with.
        */}
        <span className="flex items-baseline gap-3">
          <span
            className={`min-w-0 flex-1 text-xs leading-relaxed text-muted-foreground ${open ? "" : "line-clamp-2"}`}
          >
            {question.text}
          </span>
          <span className="flex shrink-0 items-center gap-2">
            {question.requirement === "required" && (
              <span
                className={cn(
                  "rounded border border-border px-1.5 py-px",
                  EYEBROW,
                )}
              >
                Required
              </span>
            )}
            <span className="font-mono text-[11px] tabular-nums text-muted-foreground">
              {question.id}
            </span>
          </span>
        </span>
      </button>
      {/* The model's answer, so muted and marked - it was at full contrast, which is the
          treatment for the tool's own words and the document's values.

          `prominent`, like every other result row in the suite. It was `body`, which is
          the size for a panel's own paragraph - a trace panel, the priority digest - and
          at 14px it made the answer larger than the question it answers and left the
          11px label beside it looking stranded. */}
      {question.statement && (
        <Reading size="prominent" className="mt-2">{question.statement}</Reading>
      )}
      {/*
        The ask, given its own line rather than left inside the statement. On a partial
        this is the sentence that goes back to the grantee, and burying it in prose is
        why it was required as a field in the first place.
      */}
      {/*
        The ask, given its own line rather than left inside the statement. On a partial
        this is the sentence that goes back to the grantee, and burying it in prose is why
        it was required as a field in the first place.

        Labelled rather than marked: this and the statement above are both a model's
        reading, so the authorship mark cannot separate them and neither can tone. The
        label used to sit *inside* the sentence, which put the tool's word inside a
        model's - the thing `Attributed` exists to avoid, and which Aligner had already
        solved for its two parallel sentences.
      */}
      {question.missing && (
        <Attributed label="Still not stated" continued className="mt-1.5">
          {question.missing}
        </Attributed>
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
