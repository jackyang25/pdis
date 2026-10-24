"use client";

import { memo, useCallback, useEffect, useMemo, useState } from "react";
import { useShallow } from "zustand/react/shallow";

import { CollapsibleCard } from "@/components/collapsible-card";
import { ContextFields } from "@/components/configuration-fields";
import { EmptyState } from "@/components/empty-state";
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
import { TabsContent } from "@/components/ui/tabs";
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
import { sourceDisplayLabel } from "@/lib/scout-labels";
import {
  packDrafterResult,
  runFilename,
  runLabel,
  runScope,
  unpackDrafterResult,
} from "@/lib/result-file";
import { useDrafterSession } from "@/lib/session";
import { importTool, runTool } from "@/lib/tool-run";
import { isContextComplete, useHeaderStore } from "@/lib/store";
import { toolAuthority } from "@/lib/tools";
import { countLabel } from "@/lib/count-label";

const STEPS = [
  { key: "plan", label: "Planning searches" },
  { key: "search", label: "Searching evidence" },
  { key: "evidence", label: "Reading evidence" },
  { key: "suggest", label: "Suggesting targets" },
];

export default function DrafterPage() {
  const session = useDrafterSession(
    useShallow(({ result, busy, startedAt, stage, progress, error, setError }) =>
      ({ result, busy, startedAt, stage, progress, error, setError })),
  );
  const header = useHeaderStore((state) => state.header);
  const [showSetup, setShowSetup] = useState(!session.result);

  useEffect(() => {
    if (session.result) setShowSetup(false);
  }, [session.result]);

  const contextReady = isContextComplete(header);

  function handleRun() {
    if (!contextReady) return;
    void runTool(useDrafterSession, async (report) => (await runDrafter(
      { org: header.org, intervention_class: header.intervention_class, indication: header.indication },
      report,
    )).result);
  }

  const showSetupPanel = useCallback(() => setShowSetup(true), []);

  return (
    <>
      <PageHeader title="Drafter" description={toolAuthority("drafter")} />
      <div className="flex flex-col gap-6">
        {(session.busy || !session.result || showSetup) && (
          <RunPanel
            onCancel={session.result ? () => setShowSetup(false) : undefined}
            busy={session.busy}
            startedAt={session.startedAt}
            // Drafter reads no document: it drafts from the product context alone.
            documents={null}
            onRun={handleRun}
            onImport={(file) => importTool(useDrafterSession, file, unpackDrafterResult)}
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
            onNewAnalysis={showSetupPanel}
          />
        )}
      </div>
    </>
  );
}

/** Memoized so a run's progress ticks, which re-render the page, leave a held result alone. */
const DraftView = memo(function DraftView({
  result,
  onError,
  onNewAnalysis,
}: {
  result: DraftResult;
  onError: (message: string | null) => void;
  onNewAnalysis: () => void;
}) {
  const { results, selectedId, selectResult, removeResult } = useDrafterSession(
    useShallow(({ results, selectedId, selectResult, removeResult }) =>
      ({ results, selectedId, selectResult, removeResult })),
  );
  const held = results.find((entry) => entry.id === selectedId);
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
        "Every iTPP variable for this product type, so the row sums to the number of variables. "
        + "Each target is a suggestion to check against its sources."
      }
      tabValue={tab}
      onTabChange={setTab}
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
            download={held && { filename: runFilename("drafter"), data: () => packDrafterResult(result, held) }}
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
            {shown === 0 && <EmptyState message="No variable matches that search" />}
          </ResultCardStack>
        </div>
      </TabsContent>
    </ResultLayout>
  );
});

/** Weight follows consequence: unfinished variables and failed sources in the box, absent ones as a caveat. */
function DraftNotices({ result, counts }: { result: DraftResult; counts: ReturnType<typeof countVariables> }) {
  return (
    <ResultNotices>
      {counts.failed > 0 && (
        <WarningNotice label="Variables not suggested">
          {countLabel(counts.failed, "variable")} could not be suggested because of an error.
          Run the draft again, or fill in {counts.failed === 1 ? "that row" : "those rows"} in the exported Word table.
        </WarningNotice>
      )}
      {/* A source that failed is missing from every suggestion, which changes what the draft
          says; one this deployment never offered is a limit on how far it reaches. */}
      {result.failed_sources.length > 0 && (
        <WarningNotice
          label="Sources that failed"
          summary={`${sourceList(result.failed_sources)} failed in this run, so no suggestion includes their evidence.`}
        >
          {/* The provider's own words, kept on the result so a failure can be diagnosed later. */}
          <ul className="space-y-1 text-muted-foreground">
            {result.source_errors
              .filter((error) => result.failed_sources.includes(error.source))
              .map((error) => <li key={error.source}>{sourceDisplayLabel(error.source)}: {error.message}</li>)}
          </ul>
        </WarningNotice>
      )}
      {result.unconfigured_sources.length > 0 && (
        <CaveatNotice label="Sources not available">
          Not available in this deployment: {sourceList(result.unconfigured_sources)}.
        </CaveatNotice>
      )}
    </ResultNotices>
  );
}

function sourceList(sources: string[]): string {
  return sources.map((source) => sourceDisplayLabel(source)).join(", ");
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
