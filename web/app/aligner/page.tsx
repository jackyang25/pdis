"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowRight, Plus, X } from "lucide-react";
import { CollapsibleCard } from "@/components/collapsible-card";
import { ErrorMessage } from "@/components/ui/error-message";
import { DocumentSourceProvider } from "@/components/document-source-trace";
import { FinalResultActions } from "@/components/final-result-actions";
import { PageHeader } from "@/components/page-header";
import { RunPanel, type DocumentSlot } from "@/components/run-panel";
import {
  ContextFields,
  SourceTypeField,
  useSupportedDocumentTypes,
} from "@/components/configuration-fields";
import { ConfigurationShell } from "@/components/ui/config-field";
import {
  fetchAlignerEdges,
  runAligner,
  type AlignmentEdgeSpec,
  type AlignmentResult,
} from "@/lib/api";
import {
  alignerResultFilename,
  packAlignerResult,
  unpackAlignerResult,
} from "@/lib/result-file";
import { useAlignerSession } from "@/lib/session";
import { isContextComplete, useHeaderStore } from "@/lib/store";
import { displayLabel } from "@/lib/display-label";

const STEPS = [{ key: "parse", label: "Parsing documents" }];

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
        description="Compare product-development documents against the ones they answer to."
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
          <div key={choice.key} className="flex items-end gap-1.5">
            <div className="min-w-0 flex-1">
              <SourceTypeField
                label={`Document ${index + 1}`}
                value={choice.sourceType || undefined}
                exclude={taken}
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
              disabled={disabled || choices.length <= 2}
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
  const nameOf = new Map(
    result.documents.map((document) => [document.doc_id, displayLabel(document.source_type)]),
  );
  const blockCount = (docId: string) =>
    result.blocks.filter((block) => block.doc_id === docId).length;

  return (
    <DocumentSourceProvider blocks={result.blocks}>
      <CollapsibleCard
        title="Parsed documents"
        subtitle={
          <span>
            {result.documents.map((document) => document.doc_id).join(", ")}
          </span>
        }
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
        <dl className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {result.documents.map((document) => (
            <div key={document.doc_id} className="min-w-0">
              <dt className="text-[10px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                {displayLabel(document.source_type)}
              </dt>
              <dd className="mt-1 truncate text-sm font-medium">{document.doc_id}</dd>
              <dd className="mt-0.5 text-xs text-muted-foreground">
                {blockCount(document.doc_id)} blocks
              </dd>
            </div>
          ))}
        </dl>

        <div className="mt-5 border-t border-border pt-4">
          <p className="text-xs font-medium">Comparisons</p>
          <ul className="mt-2 flex flex-col gap-2.5">
            {result.edges.map((edge) => (
              <li key={`${edge.reference_doc_id}-${edge.comparison_doc_id}`}>
                <p className="flex items-center gap-1.5 text-xs font-medium">
                  <span>{nameOf.get(edge.reference_doc_id)}</span>
                  <ArrowRight aria-label="compared against" className="h-3 w-3 text-muted-foreground" />
                  <span>{nameOf.get(edge.comparison_doc_id)}</span>
                </p>
                <p className="mt-0.5 text-[11px] leading-4 text-muted-foreground">
                  {edge.question}
                </p>
              </li>
            ))}
          </ul>
        </div>

        <p className="mt-5 border-t border-border pt-3 text-xs leading-5 text-muted-foreground">
          Every document is parsed and citable, and the comparisons above are the
          ones a run will make. Aligner reports no findings against them yet: its
          analysis was removed and the shape that replaces it is still being
          designed.
        </p>
      </CollapsibleCard>
    </DocumentSourceProvider>
  );
}
