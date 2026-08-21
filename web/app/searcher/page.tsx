"use client";

import { FormEvent, useEffect, useState } from "react";
import { ExternalLink, Loader2, Search } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { ErrorMessage } from "@/components/ui/error-message";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";
import { fetchSearchSources, runSearcher, type SearchLane, type SearchSource } from "@/lib/api";
import { RunHistory } from "@/components/run-history";
import { runLabel } from "@/lib/result-file";
import { useSearcherSession } from "@/lib/session";
import { SourceAttributions } from "@/components/source-attributions";
import type { Finding } from "@/lib/api";

export default function SearcherPage() {
  const [query, setQuery] = useState("");
  const [condition, setCondition] = useState("");
  const [intervention, setIntervention] = useState("");
  const [sources, setSources] = useState<SearchSource[]>([]);
  const [sourcesLoaded, setSourcesLoaded] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const { result, busy, error, addResult, setResult, setBusy, setStage, setError } =
    useSearcherSession();

  useEffect(() => {
    let active = true;
    fetchSearchSources()
      .then((available) => {
        if (!active) return;
        setSources(available);
        setSelected(
          new Set(
            available.filter((source) => source.default_enabled).map((source) => source.key),
          ),
        );
      })
      .catch((cause) => {
        if (active) setError((cause as Error).message);
      })
      .finally(() => {
        if (active) setSourcesLoaded(true);
      });
    return () => {
      active = false;
    };
  }, [setError]);

  function toggle(id: string) {
    const source = sources.find((candidate) => candidate.key === id);
    if (!source?.configured || !reachable(source)) return;
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const canRun = query.trim().length > 0 && selected.size > 0 && !busy;
  const unreachableLabels = sources
    .filter((source) => source.configured && !reachable(source))
    .map((source) => source.label);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!canRun) return;
    setBusy(true);
    setError(null);
    setStage("search");
    setResult(null);
    try {
      const res = await runSearcher(
        query.trim(),
        Array.from(selected),
        { condition: condition.trim(), intervention: intervention.trim() },
        setStage,
      );
      addResult(res);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
      setStage(null);
    }
  }

  return (
    <>
      <PageHeader title="Searcher" description="Search registered evidence sources through one normalized workspace." />
      <div className="flex flex-col gap-6">
        <form onSubmit={onSubmit} className="rounded-lg border border-border bg-card p-5">
          <div className="flex flex-col gap-2 sm:flex-row">
            <div className="relative flex-1">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="e.g. recent FDA guidance on RSV vaccines"
                className="h-9 w-full rounded-md border border-input bg-background pl-9 pr-3 text-sm outline-none placeholder:text-muted-foreground focus:ring-2 focus:ring-ring/20 disabled:cursor-not-allowed disabled:opacity-50"
                disabled={busy}
              />
            </div>
            <Button className="min-w-[6.5rem]" type="submit" disabled={!canRun}>
              {busy ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Searching
                </>
              ) : (
                "Search"
              )}
            </Button>
          </div>
          {/*
            The two facets the field-addressed sources anchor on. Styled like the query
            input above rather than through the rail primitives, because this card is not
            a configuration rail and `ConfigFieldGrid` exists to solve the rail's 17rem
            problem, which does not apply here. The notes are not decoration: left blank,
            an adapter anchors on the query text itself, and a reader who does not know
            that reads six empty lanes as an absence of evidence.
          */}
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <div className="min-w-0">
              <div className="mb-1.5">
                <Label>Condition</Label>
              </div>
              <input
                type="text"
                value={condition}
                onChange={(e) => setCondition(e.target.value)}
                placeholder="e.g. resected melanoma"
                className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm outline-none placeholder:text-muted-foreground focus:ring-2 focus:ring-ring/20 disabled:cursor-not-allowed disabled:opacity-50"
                disabled={busy}
              />
              <p className="mt-1.5 text-xs text-muted-foreground">
                Anchors every registry and database request. Left blank, they anchor on the
                query text instead, which rarely matches a condition field.
              </p>
            </div>
            <div className="min-w-0">
              <div className="mb-1.5">
                <Label>Intervention</Label>
              </div>
              <input
                type="text"
                value={intervention}
                onChange={(e) => setIntervention(e.target.value)}
                placeholder="e.g. pembrolizumab"
                className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm outline-none placeholder:text-muted-foreground focus:ring-2 focus:ring-ring/20 disabled:cursor-not-allowed disabled:opacity-50"
                disabled={busy}
              />
              <p className="mt-1.5 text-xs text-muted-foreground">
                Narrows those requests to one product. Ignored by sources whose grammar has
                no intervention field.
              </p>
            </div>
          </div>
          <div className="mt-4 flex min-h-8 flex-wrap items-center gap-2">
            <span className="mr-1 text-xs text-muted-foreground">Sources</span>
            {!sourcesLoaded && (
              <>
                <span className="h-8 w-20 rounded-md border border-border bg-muted/40" />
                <span className="h-8 w-24 rounded-md border border-border bg-muted/40" />
                <span className="h-8 w-16 rounded-md border border-border bg-muted/40" />
              </>
            )}
            {sources.map((source) => {
              const on = selected.has(source.key);
              const unreachable = !reachable(source);
              return (
                <button
                  key={source.key}
                  type="button"
                  onClick={() => toggle(source.key)}
                  disabled={busy || !source.configured || unreachable}
                  title={
                    !source.configured
                      ? "Backend connector not configured"
                      : unreachable
                        ? `Needs a document-stated ${source.required_entity_types.join(" or ")}, which a free-text search has none of. Reachable from Scout, which reads a profile.`
                        : undefined
                  }
                  aria-pressed={on}
                  className={cn(
                    "h-8 rounded-md border px-3 text-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/20 disabled:opacity-50 motion-reduce:transition-none",
                    on
                      ? "border-foreground bg-foreground text-background"
                      : "border-border bg-background text-muted-foreground hover:text-foreground",
                  )}
                >
                  {source.label}
                </button>
              );
            })}
            {sourcesLoaded && selected.size === 0 && (
              <span className="text-xs text-destructive">Select at least one source.</span>
            )}
          </div>
          {/*
            Stated rather than left to a tooltip. A dimmed control with no visible reason
            is the same defect as a lane that returns nothing without saying why.
          */}
          {unreachableLabels.length > 0 && (
            <p className="mt-2 text-xs text-muted-foreground">
              {unreachableLabels.join(", ")} address their API by a named gene, protein or
              compound, which comes from a parsed document. Reach them through Scout.
            </p>
          )}
        </form>

        {error && <ErrorMessage>{error}</ErrorMessage>}

        {result && <Findings result={result} sources={sources} />}
      </div>
    </>
  );
}

function Findings({
  result,
  sources,
}: {
  result: { query: string; findings: Finding[]; lanes?: SearchLane[] };
  sources: SearchSource[];
}) {
  const { results, selectedId, selectResult, removeResult } = useSearcherSession();
  const labels = new Map(sources.map((source) => [source.key, source.label]));

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2 pb-1 text-sm text-muted-foreground">
        <p>
          {result.findings.length} finding{result.findings.length === 1 ? "" : "s"} for &quot;{result.query}&quot;
        </p>
        <span className="flex items-center gap-2">
          <RunHistory
            runs={results}
            selectedId={selectedId}
            onSelect={selectResult}
            onRemove={removeResult}
            label={(value) => runLabel(value, "searcher")}
          />
        </span>
      </div>
      <Lanes lanes={result.lanes ?? []} labels={labels} />
      {result.findings.map((finding) => (
        <article key={finding.url} className="rounded-lg border border-border bg-card p-4">
          <div className="flex items-start gap-3">
            <Badge variant="muted">{labels.get(finding.source) ?? humanizeSource(finding.source)}</Badge>
            <a
              href={finding.url}
              target="_blank"
              rel="noreferrer"
              className="flex-1 text-sm font-medium leading-snug text-foreground hover:underline"
            >
              {finding.title}
            </a>
            <ExternalLink className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          </div>
          <p className="mt-2 truncate font-mono text-[10px] text-muted-foreground/70">{finding.url}</p>
          {finding.excerpt ? (
            <p className="mt-3 whitespace-pre-wrap text-sm leading-relaxed">{finding.excerpt}</p>
          ) : (
            <p className="mt-3 text-xs italic text-muted-foreground">
              No cited excerpt - model did not quote this source.
            </p>
          )}
        </article>
      ))}
      <SourceAttributions findings={result.findings} />
    </div>
  );
}

/**
 * What every selected source did, including the ones that produced nothing.
 *
 * The counted breakdown this replaced was derived from the findings, so a source that
 * returned nothing, was skipped, or failed outright did not appear at all — all three
 * rendered as absence, and absence read as "no evidence exists". These rows come from
 * the run's outcomes instead, which keep the three distinct.
 *
 * The query shown is the native one the provider received. For a field-addressed source
 * that is not the text typed into the box, and the difference is usually the explanation
 * for a zero.
 *
 * Counts are per request, before cross-lane deduplication, so they can add up to more
 * than the number of findings shown. Labelled "returned" for that reason: the header
 * above owns the number of findings, and these rows own what each source sent back.
 */
function Lanes({
  lanes,
  labels,
}: {
  lanes: SearchLane[];
  labels: Map<string, string>;
}) {
  if (lanes.length === 0) return null;
  return (
    <div className="rounded-lg border border-border bg-card">
      <p className="border-b border-border px-4 py-2 text-xs text-muted-foreground">
        Sources searched
      </p>
      <ul className="divide-y divide-border">
        {lanes.map((lane, at) => (
          <li
            key={`${lane.source}-${at}`}
            className="flex flex-wrap items-baseline gap-x-3 gap-y-1 px-4 py-2.5 text-xs"
          >
            <span className="min-w-[8rem] font-medium text-foreground">
              {labels.get(lane.source) ?? humanizeSource(lane.source)}
            </span>
            <code className="min-w-0 flex-1 break-all font-mono text-[10px] text-muted-foreground">
              {/* A ruled-out lane never built a request, so there is no query to show. */}
              {lane.query || (lane.status === "skipped" ? "no request sent" : "")}
            </code>
            {lane.status === "complete" ? (
              <span
                className={cn(
                  "shrink-0 tabular-nums",
                  lane.returned === 0 ? "text-muted-foreground" : "text-foreground",
                )}
              >
                {lane.returned} returned
              </span>
            ) : (
              <span
                className={cn(
                  "shrink-0",
                  lane.status === "failed" ? "text-destructive" : "text-muted-foreground",
                )}
              >
                {lane.status}
                {lane.detail ? `: ${lane.detail}` : ""}
              </span>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * Whether this source can be searched from a free-text query at all.
 *
 * A source declaring `required_entity_types` addresses its API by a named subject - a
 * gene, a protein, a compound - and those come from a parsed document. This page has no
 * document, so such a source can never build a request here. The planner rules it out
 * and reports the reason, but offering a control whose only outcome is a skip row states
 * something untrue about what this interface accepts.
 *
 * Read from the source's own declaration rather than a list kept here, so adding a
 * document-addressed source needs no change on this page. The decision is still the
 * planner's: this only declines to offer a button for an outcome the planner has
 * already determined.
 */
function reachable(source: SearchSource): boolean {
  return source.required_entity_types.length === 0;
}

function humanizeSource(source: string): string {
  return source
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}
