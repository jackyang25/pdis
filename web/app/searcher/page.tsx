"use client";

import { FormEvent, useState } from "react";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { runSearcher } from "@/lib/api";
import { useSearcherSession } from "@/lib/session";

export default function SearcherPage() {
  const [query, setQuery] = useState("");
  const { result, busy, stage, error, setResult, setBusy, setStage, setError } =
    useSearcherSession();

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const trimmedQuery = query.trim();
    if (!trimmedQuery || busy) return;

    setBusy(true);
    setError(null);
    setStage("search");
    setResult(null);
    try {
      const res = await runSearcher(trimmedQuery, setStage);
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
      <PageHeader
        title="Searcher"
        description="Run a web search query and inspect source-attributed findings."
      />
      <div className="flex max-w-3xl flex-col gap-6">
        <form onSubmit={onSubmit} className="flex gap-2">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="e.g. recent FDA guidance on RSV vaccines"
            className="min-h-10 flex-1 rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm outline-none transition-colors placeholder:text-muted-foreground focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
            disabled={busy}
          />
          <Button type="submit" disabled={busy || !query.trim()}>
            {busy ? "Searching..." : "Search"}
          </Button>
        </form>

        {busy && stage && (
          <p className="text-sm text-muted-foreground">Stage: {stage}</p>
        )}
        {error && <p className="text-sm text-destructive">{error}</p>}

        {result && (
          <div className="space-y-4">
            <p className="text-sm text-muted-foreground">
              {result.findings.length} finding
              {result.findings.length === 1 ? "" : "s"} for "{result.query}"
            </p>
            {result.findings.map((finding) => (
              <article key={finding.url} className="rounded-md border bg-background p-4">
                <a
                  href={finding.url}
                  target="_blank"
                  rel="noreferrer"
                  className="font-medium underline underline-offset-4"
                >
                  {finding.title}
                </a>
                <p className="mt-1 break-all text-xs text-muted-foreground">
                  {finding.url}
                </p>
                {finding.excerpt ? (
                  <p className="mt-3 whitespace-pre-wrap text-sm leading-relaxed">
                    {finding.excerpt}
                  </p>
                ) : (
                  <p className="mt-3 text-xs italic text-muted-foreground">
                    No cited excerpt - model did not quote this source.
                  </p>
                )}
              </article>
            ))}
          </div>
        )}
      </div>
    </>
  );
}
