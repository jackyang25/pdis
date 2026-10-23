"use client";

import { useEffect, useMemo, useState } from "react";

import { CollapsibleCard } from "@/components/collapsible-card";
import { ContextFields } from "@/components/configuration-fields";
import { DrafterExportButton } from "@/components/drafter-export-button";
import { DrafterSignalHelp } from "@/components/drafter-signal-help";
import { DrafterVariableRow } from "@/components/drafter-variable";
import { FinalResultActions } from "@/components/final-result-actions";
import { PageHeader } from "@/components/page-header";
import { RunHistory } from "@/components/run-history";
import { RunPanel } from "@/components/run-panel";
import { ConfigurationShell } from "@/components/ui/config-field";
import { ErrorMessage } from "@/components/ui/error-message";
import { MetricsRow } from "@/components/ui/metrics-row";
import { ResultCardStack } from "@/components/ui/result-card-stack";
import { ResultLayout } from "@/components/ui/result-layout";
import { ResultSearch } from "@/components/ui/result-search";
import { ResultToolbar, ResultToolbarEnd } from "@/components/ui/result-toolbar";
import { TabsContent, TabsTrigger } from "@/components/ui/tabs";
import { CaveatNotice, ResultNotices, WarningNotice } from "@/components/ui/warning-notice";
import { runDrafter, type DraftResult } from "@/lib/api";
import {
  DRAFTER_PANELS,
  countVariables,
  drafterMetricItems,
  panelVariables,
  type DrafterPanelId,
} from "@/lib/drafter-presentation";
import { normalizeQuery } from "@/lib/result-search";
import {
  packDrafterResult,
  readResultIdentity,
  runFilename,
  runLabel,
  runScope,
  unpackDrafterResult,
} from "@/lib/result-file";
import { useDrafterSession } from "@/lib/session";
import { isContextComplete, useHeaderStore } from "@/lib/store";
import { toolAuthority } from "@/lib/tools";

const STEPS = [
  { key: "plan", label: "Planning searches" },
  { key: "search", label: "Searching evidence" },
  { key: "evidence", label: "Reading evidence" },
  { key: "suggest", label: "Suggesting targets" },
];

export default function DrafterPage() {
  const session = useDrafterSession();
  const header = useHeaderStore((state) => state.header);
  const [showSetup, setShowSetup] = useState(!session.result);

  useEffect(() => {
    if (session.result) setShowSetup(false);
  }, [session.result]);

  const contextReady = isContextComplete(header);

  async function handleRun() {
    if (!contextReady) return;
    session.setBusy(true);
    session.setError(null);
    session.setStage(null);
    session.setProgress(null);
    try {
      const response = await runDrafter(
        { org: header.org, intervention_class: header.intervention_class, indication: header.indication },
        (stage, progress) => {
          session.setStage(stage);
          session.setProgress(progress ?? null);
        },
      );
      session.addResult(response.result);
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
      session.addResult(unpackDrafterResult(raw), readResultIdentity(raw));
    } catch (error) {
      session.setError(`Could not import result: ${(error as Error).message}`);
    }
  }

  return (
    <>
      <PageHeader title="Drafter" description={toolAuthority("drafter")} />
      <div className="flex flex-col gap-6">
        {(session.busy || !session.result || showSetup) && (
          <RunPanel
            busy={session.busy}
            startedAt={session.startedAt}
            // Drafter reads no document: it drafts from the product context alone.
            documents={null}
            onRun={() => void handleRun()}
            onImport={(file) => void handleImport(file)}
            steps={STEPS}
            currentStage={session.stage}
            progress={session.progress}
            runDisabled={!contextReady}
            hint={contextReady ? undefined : "Complete the configuration to run."}
            runLabel="Draft targets"
            busyLabel="Drafting"
            configuration={
              <ConfigurationShell>
                <ContextFields />
              </ConfigurationShell>
            }
          />
        )}

        {session.error && <ErrorMessage>{session.error}</ErrorMessage>}
        {session.result && (
          <DraftView
            result={session.result}
            onError={session.setError}
            onNewAnalysis={() => setShowSetup(true)}
          />
        )}
      </div>
    </>
  );
}

function DraftView({
  result,
  onError,
  onNewAnalysis,
}: {
  result: DraftResult;
  onError: (message: string | null) => void;
  onNewAnalysis: () => void;
}) {
  const { results, selectedId, selectResult, removeResult } = useDrafterSession();
  const [tab, setTab] = useState("targets");
  const [query, setQuery] = useState("");
  const normalizedQuery = normalizeQuery(query);
  const counts = useMemo(() => countVariables(result), [result]);
  const shown = useMemo(
    () => DRAFTER_PANELS.reduce((sum, panel) => sum + panelVariables(result, panel.id, normalizedQuery).length, 0),
    [result, normalizedQuery],
  );

  return (
    <ResultLayout
      notices={<DraftNotices result={result} counts={counts} />}
      title={runLabel(result, "drafter")}
      subtitle={runScope(result, "drafter")}
      metrics={<MetricsRow total={counts.total} unit={["variable", "variables"]} items={drafterMetricItems(result)} />}
      metricsNote={
        "Every variable of the iTPP for this product type, so the row sums to the number of variables. "
        + "Suggested and not enough evidence are the run's readings, so they show even at zero. "
        + "Every target is a suggestion to check against its sources and edit in your iTPP."
      }
      tabValue={tab}
      onTabChange={setTab}
      tabs={<TabsTrigger value="targets">Targets</TabsTrigger>}
      actions={
        <>
          <RunHistory
            runs={results}
            selectedId={selectedId}
            onSelect={selectResult}
            onRemove={removeResult}
            label={(value) => runLabel(value, "drafter")}
          />
          <FinalResultActions
            onNewAnalysis={onNewAnalysis}
            download={{ filename: runFilename("drafter"), data: packDrafterResult(result) }}
          />
          <DrafterExportButton result={result} onError={onError} />
        </>
      }
    >
      <TabsContent value="targets" className="m-0">
        <ResultToolbar>
          <ResultSearch label="Search variables" placeholder="Find a variable…" value={query} onChange={setQuery} />
          <ResultToolbarEnd count={{ shown, total: counts.total }}>
            <DrafterSignalHelp />
          </ResultToolbarEnd>
        </ResultToolbar>
        <div className="flex flex-col gap-6 px-5 py-5 sm:px-6">
          <ResultCardStack>
            {DRAFTER_PANELS.map((panel) => (
              <DraftPanel key={panel.id} panel={panel} result={result} query={normalizedQuery} />
            ))}
          </ResultCardStack>
        </div>
      </TabsContent>
    </ResultLayout>
  );
}

/** Weight follows consequence: unfinished variables and failed sources in the box, absent ones as a caveat. */
function DraftNotices({ result, counts }: { result: DraftResult; counts: ReturnType<typeof countVariables> }) {
  return (
    <ResultNotices>
      {counts.failed > 0 && (
        <WarningNotice label="Variables not suggested">
          {counts.failed} {counts.failed === 1 ? "variable" : "variables"} could not be suggested. Run the draft
          again, or write {counts.failed === 1 ? "its target" : "their targets"} yourself.
        </WarningNotice>
      )}
      {/* A source that failed is missing from every suggestion, which changes what the draft
          says; one this deployment never offered is a limit on how far it reaches. */}
      {result.failed_sources.length > 0 && (
        <WarningNotice
          label="Sources that failed"
          summary={`${result.failed_sources.join(", ")} failed in this run, so no suggestion includes their evidence.`}
        >
          {/* The provider's own words, kept on the result so a failure can be diagnosed later. */}
          <ul className="space-y-1 text-muted-foreground">
            {result.source_errors
              .filter((error) => result.failed_sources.includes(error.source))
              .map((error) => <li key={error.source}>{error.source}: {error.message}</li>)}
          </ul>
        </WarningNotice>
      )}
      {result.unconfigured_sources.length > 0 && (
        <CaveatNotice label="Sources not available">
          Not available in this deployment: {result.unconfigured_sources.join(", ")}.
        </CaveatNotice>
      )}
    </ResultNotices>
  );
}

function DraftPanel({
  panel,
  result,
  query,
}: {
  panel: (typeof DRAFTER_PANELS)[number];
  result: DraftResult;
  query: string;
}) {
  const variables = panelVariables(result, panel.id as DrafterPanelId, query);
  if (variables.length === 0) return null;
  return (
    <CollapsibleCard
      title={panel.title}
      count={variables.length}
      subtitle={panel.description}
      key={query ? "filtered" : "all"}
      // Suggestions are what a reader came for, so that panel opens on arrival.
      defaultOpen={panel.id === "suggested" || Boolean(query)}
    >
      <ul className="divide-y divide-border/60">
        {variables.map((variable) => (
          <DrafterVariableRow key={variable.name} variable={variable} />
        ))}
      </ul>
    </CollapsibleCard>
  );
}
