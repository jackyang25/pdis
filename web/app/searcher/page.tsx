"use client";

import { FormEvent, useEffect, useState } from "react";
import { ExternalLink, Loader2, Search } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { fetchSearchSources, runSearcher, type SearchSource } from "@/lib/api";
import { useSearcherSession } from "@/lib/session";
import { SourceAttributions } from "@/components/source-attributions";
import type { Finding } from "@/lib/api";

export default function SearcherPage() {
  const [query, setQuery] = useState("");
  const [sources, setSources] = useState<SearchSource[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const { result, busy, stage, error, setResult, setBusy, setStage, setError } =
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
      });
    return () => {
      active = false;
    };
  }, [setError]);

  function toggle(id: string) {
    if (!sources.find((source) => source.key === id)?.configured) return;
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const canRun = query.trim().length > 0 && selected.size > 0 && !busy;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!canRun) return;
    setBusy(true);
    setError(null);
    setStage("search");
    setResult(null);
    try {
      const res = await runSearcher(query.trim(), Array.from(selected), setStage);
      setResult(res);
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
            <Button type="submit" disabled={!canRun}>
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
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <span className="mr-1 text-xs text-muted-foreground">Sources</span>
            {sources.map((source) => {
              const on = selected.has(source.key);
              return (
                <button
                  key={source.key}
                  type="button"
                  onClick={() => toggle(source.key)}
                  disabled={busy || !source.configured}
                  title={source.configured ? undefined : "Backend connector not configured"}
                  aria-pressed={on}
                  className={cn(
                    "h-8 rounded-full border px-3 text-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/20 disabled:opacity-50",
                    on
                      ? "border-foreground bg-foreground text-background"
                      : "border-border bg-background text-muted-foreground hover:text-foreground",
                  )}
                >
                  {source.label}
                </button>
              );
            })}
            {selected.size === 0 && (
              <span className="text-xs text-destructive">Select at least one source.</span>
            )}
          </div>
        </form>

        {busy && stage && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            Searching across {selected.size} source lanes…
          </div>
        )}
        {error && <p className="text-sm text-destructive">{error}</p>}

        {result && <Findings result={result} sources={sources} />}
      </div>
    </>
  );
}

function Findings({ result, sources }: { result: { query: string; findings: Finding[] }; sources: SearchSource[] }) {
  const labels = new Map(sources.map((source) => [source.key, source.label]));
  const counts = result.findings.reduce<Record<string, number>>((acc, f) => {
    acc[f.source] = (acc[f.source] ?? 0) + 1;
    return acc;
  }, {});
  const breakdown = Object.entries(counts)
    .map(([src, n]) => `${labels.get(src) ?? humanizeSource(src)} ${n}`)
    .join(" · ");

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2 pb-1 text-sm text-muted-foreground">
        <p>
          {result.findings.length} finding{result.findings.length === 1 ? "" : "s"} for &quot;{result.query}&quot;
        </p>
        {breakdown && <span className="text-xs">{breakdown}</span>}
      </div>
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

function humanizeSource(source: string): string {
  return source
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}
