"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ChevronRight } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { CONTENT_ARRIVAL_MOTION } from "@/lib/motion";
import { promptAnchor, type ToolKey } from "@/lib/prompt-reference";
import { cn } from "@/lib/utils";

type PromptEntry = {
  tool: ToolKey;
  id: string;
  stage: string;
  title: string;
  framing_slot: string | null;
  produces: { result_fields: string[]; ui_labels: string[] };
  text: string;
};

type Reference = {
  version: number;
  prompts: PromptEntry[];
};

// Roughly 100 KB of instruction text that almost nobody opens, so it is fetched
// on first expansion instead of shipping inside the page bundle.
const REFERENCE_URL = "/prompt-reference.json";

export function PromptReference({ tool }: { tool: ToolKey }) {
  const [reference, setReference] = useState<Reference | null>(null);
  const [status, setStatus] = useState<"idle" | "loading" | "failed">("idle");
  // Expanding two entries in one tick would otherwise read a stale `status` and
  // request the file twice; the in-flight promise makes them share one fetch.
  const inFlight = useRef<Promise<void> | null>(null);

  const load = useCallback(() => {
    if (reference) return inFlight.current;
    if (inFlight.current) return inFlight.current;
    setStatus("loading");
    inFlight.current = (async () => {
      try {
        const response = await fetch(REFERENCE_URL);
        if (!response.ok) throw new Error(String(response.status));
        setReference((await response.json()) as Reference);
        setStatus("idle");
      } catch {
        setStatus("failed");
        inFlight.current = null;
      }
    })();
    return inFlight.current;
  }, [reference]);

  // A reader following "Read the instructions behind this" should land on the
  // open prompt, not on a closed row they have to click again.
  useEffect(() => {
    const openFromHash = () => {
      const id = window.location.hash.slice(1);
      if (!id.startsWith("prompt-")) return;
      const entry = document.getElementById(id);
      if (!(entry instanceof HTMLDetailsElement)) return;
      entry.open = true;
      void load();
      entry.scrollIntoView({ block: "start" });
    };
    openFromHash();
    window.addEventListener("hashchange", openFromHash);
    return () => window.removeEventListener("hashchange", openFromHash);
  }, [load]);

  // Stages come from the published reference in publication order, so adding a
  // prompt to a catalog surfaces it here without touching this file.
  const stages = reference
    ? [...new Set(reference.prompts.filter((p) => p.tool === tool).map((p) => p.stage))]
    : [];

  return (
    <div className="mt-4">
      <p className="max-w-[75ch] text-xs leading-5 text-muted-foreground">
        Each stage below sends these instructions with every run. Your document&apos;s
        own content is inserted where a slot appears, so {"{field_name}"} and
        {" {section_name}"} mark where the document&apos;s own values go. The response
        schema each stage requires is not shown.
      </p>

      {status === "failed" ? (
        <p className="mt-4 text-xs text-muted-foreground">
          Unable to load the prompt reference.{" "}
          <button
            type="button"
            onClick={() => {
              setStatus("idle");
              void load();
            }}
            className="underline underline-offset-2 hover:text-foreground"
          >
            Try again
          </button>
        </p>
      ) : null}

      {reference === null ? (
        <button
          type="button"
          onClick={() => void load()}
          disabled={status === "loading"}
          className="mt-4 inline-flex min-h-8 items-center rounded-md border border-border bg-background px-3 text-xs font-medium transition-colors hover:border-foreground/25 disabled:opacity-60 motion-reduce:transition-none"
        >
          {status === "loading" ? "Loading instructions…" : "Show the instructions"}
        </button>
      ) : (
        <div className={cn("mt-4 divide-y divide-border border-y border-border", CONTENT_ARRIVAL_MOTION)}>
          {stages.map((stage) => {
            const prompts = reference.prompts.filter(
              (prompt) => prompt.tool === tool && prompt.stage === stage,
            );
            return (
              <details
                key={stage}
                id={promptAnchor(tool, stage)}
                // Matches the sections' scroll-mt-24 so arriving via a link does
                // not park the title under the sticky header.
                className="group scroll-mt-24 py-3.5"
              >
                <summary className="flex cursor-pointer list-none items-center justify-between gap-4 text-xs font-medium [&::-webkit-details-marker]:hidden">
                  <span className="min-w-0">
                    {prompts[0]?.title ?? stage}
                    {prompts.length > 1 && (
                      <span className="ml-2 font-normal text-muted-foreground">
                        {prompts.length} prompts
                      </span>
                    )}
                  </span>
                  <ChevronRight
                    className="h-3.5 w-3.5 shrink-0 text-muted-foreground transition-transform group-open:rotate-90 motion-reduce:transition-none"
                    aria-hidden="true"
                  />
                </summary>

                <div className="mt-3">
                  {prompts.map((prompt) => (
                    <div key={prompt.id} className="mb-5 last:mb-0">
                      {/* The summary already carries the title of a lone prompt;
                          a per-prompt title only distinguishes siblings. */}
                      {prompts.length > 1 && (
                        <p className="text-[11px] font-medium text-foreground">
                          {prompt.title}
                        </p>
                      )}
                      <p
                        className={cn(
                          "text-[10px] text-muted-foreground",
                          prompts.length > 1 && "mt-1",
                        )}
                      >
                        Produces {prompt.produces.result_fields.join(", ")}
                        {prompt.framing_slot
                          ? ` · inserts the configured ${prompt.framing_slot.replace(/_/g, " ")}`
                          : ""}
                      </p>
                      <pre className="mt-2 overflow-x-auto rounded-md border border-border bg-muted/20 p-3 text-[10px] leading-[1.55] text-muted-foreground">
                        <code className="whitespace-pre-wrap break-words">
                          {prompt.text}
                        </code>
                      </pre>
                    </div>
                  ))}
                </div>
              </details>
            );
          })}
        </div>
      )}

      {reference !== null && stages.length === 0 && (
        <p className="mt-4 text-xs text-muted-foreground">
          This tool sends no model instructions. Its behaviour is deterministic.
        </p>
      )}

      {status === "loading" && reference === null && (
        <div className="mt-4 space-y-2" role="status" aria-label="Loading instructions">
          <Skeleton className="h-3 w-40" />
          <Skeleton className="h-2.5 w-64" />
          <Skeleton className="h-24" />
        </div>
      )}
    </div>
  );
}
