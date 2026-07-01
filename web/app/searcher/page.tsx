"use client";

import { FormEvent, useState } from "react";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { runSearcher } from "@/lib/api";
import { useSearcherSession } from "@/lib/session";

// Mirrors the backend's VALID_BACKENDS. The searcher service unions these lanes.
const BACKENDS = [
  { id: "web", label: "Web" },
  { id: "pubmed", label: "PubMed" },
  { id: "clinicaltrials", label: "ClinicalTrials.gov" },
] as const;

const SOURCE_LABEL: Record<string, string> = {
  web: "Web",
  pubmed: "PubMed",
  clinicaltrials: "ClinicalTrials.gov",
};

export default function SearcherPage() {
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<Set<string>>(
    new Set(BACKENDS.map((b) => b.id)),
  );
  const { result, busy, stage, error, setResult, setBusy, setStage, setError } =
    useSearcherSession();

  function toggle(id: string) {
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
      <PageHeader title="Searcher" />
      <div className="flex max-w-3xl flex-col gap-4">
        <form onSubmit={onSubmit} className="flex flex-col gap-3">
          <div className="flex gap-2">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="e.g. recent FDA guidance on RSV vaccines"
              className="min-h-10 flex-1 rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm outline-none transition-colors placeholder:text-muted-foreground focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
              disabled={busy}
            />
            <Button type="submit" disabled={!canRun}>
              {busy ? "Searching..." : "Search"}
            </Button>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs text-muted-foreground">Backends:</span>
            {BACKENDS.map((b) => {
              const on = selected.has(b.id);
              return (
                <button
                  key={b.id}
                  type="button"
                  onClick={() => toggle(b.id)}
                  disabled={busy}
                  aria-pressed={on}
                  className={cn(
                    "rounded-full border px-3 py-1 text-xs font-medium transition-colors disabled:opacity-50",
                    on
                      ? "border-foreground bg-foreground text-background"
                      : "border-border bg-background text-muted-foreground hover:text-foreground",
                  )}
                >
                  {b.label}
                </button>
              );
            })}
            {selected.size === 0 && (
              <span className="text-xs text-destructive">Select at least one backend.</span>
            )}
          </div>
        </form>

        {busy && stage && <p className="text-sm text-muted-foreground">Searching…</p>}
        {error && <p className="text-sm text-destructive">{error}</p>}

        {result && <Findings result={result} />}
      </div>
    </>
  );
}

function Findings({ result }: { result: { query: string; findings: Array<{ url: string; title: string; excerpt: string | null; source: string }> } }) {
  const counts = result.findings.reduce<Record<string, number>>((acc, f) => {
    acc[f.source] = (acc[f.source] ?? 0) + 1;
    return acc;
  }, {});
  const breakdown = Object.entries(counts)
    .map(([src, n]) => `${SOURCE_LABEL[src] ?? src} ${n}`)
    .join(" · ");

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        {result.findings.length} finding{result.findings.length === 1 ? "" : "s"} for &quot;{result.query}&quot;
        {breakdown && <span className="text-muted-foreground"> · {breakdown}</span>}
      </p>
      {result.findings.map((finding) => (
        <article key={finding.url} className="rounded-md border bg-background p-4">
          <div className="flex items-center gap-2">
            <Badge variant="muted">{SOURCE_LABEL[finding.source] ?? finding.source}</Badge>
            <a
              href={finding.url}
              target="_blank"
              rel="noreferrer"
              className="font-medium underline underline-offset-4"
            >
              {finding.title}
            </a>
          </div>
          <p className="mt-1 break-all text-xs text-muted-foreground">{finding.url}</p>
          {finding.excerpt ? (
            <p className="mt-3 whitespace-pre-wrap text-sm leading-relaxed">{finding.excerpt}</p>
          ) : (
            <p className="mt-3 text-xs italic text-muted-foreground">
              No cited excerpt - model did not quote this source.
            </p>
          )}
        </article>
      ))}
    </div>
  );
}
