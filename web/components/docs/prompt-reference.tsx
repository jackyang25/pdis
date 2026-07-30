"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ChevronRight } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { CONTENT_ARRIVAL_MOTION } from "@/lib/motion";
import { cn } from "@/lib/utils";

type PromptEntry = {
  id: string;
  stage: string;
  title: string;
  framing_slot: string | null;
  produces: { result_fields: string[]; ui_labels: string[] };
  text: string;
};

type FramingEntry = {
  key: string;
  org: string;
  source_type: string;
  intervention_class: string;
  text: string;
};

type Reference = {
  version: number;
  prompts: PromptEntry[];
  framings: FramingEntry[];
};

// Roughly 90 KB of instruction text that almost nobody opens, so it is fetched
// on first expansion instead of shipping inside the page bundle.
const REFERENCE_URL = "/prompt-reference.json";

// The same wording the signal popovers use, so a reader recognises the label
// they arrived from.
const SIGNAL_LABEL: Record<string, string> = {
  relationships: "Evidence relationships",
  grounding: "Grounding",
  alignment: "Quantitative calibration",
  precedent: "Precedent",
};

export function PromptReference() {
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

  return (
    <div className="mt-6" id="prompts">
      <p className="max-w-[75ch] text-xs leading-5 text-muted-foreground">
        Each stage below sends these instructions with every run. Your document&apos;s
        own content is inserted where a slot appears, so {"{field_name}"} and
        {" {document_target}"} mark where a field and its target go. The response
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

      <div className="mt-4 divide-y divide-border border-y border-border">
        {STAGE_ORDER.map((stage) => (
          <details
            key={stage.stage}
            id={`prompt-${stage.stage}`}
            // Matches the sections' scroll-mt-24 so arriving via a link does not
            // park the title under the sticky header.
            className="group scroll-mt-24 py-3.5"
            onToggle={(event) => {
              if (event.currentTarget.open) void load();
            }}
          >
            <summary className="flex cursor-pointer list-none items-center justify-between gap-4 text-xs font-medium [&::-webkit-details-marker]:hidden">
              <span className="min-w-0">
                {stage.title}
                <span className="ml-2 font-normal text-muted-foreground">
                  {stage.description}
                </span>
              </span>
              <ChevronRight
                className="h-3.5 w-3.5 shrink-0 text-muted-foreground transition-transform group-open:rotate-90 motion-reduce:transition-none"
                aria-hidden="true"
              />
            </summary>

            <div className="mt-3">
              {reference === null ? (
                status === "loading" ? (
                  // The shape is known: a title, a provenance line, and a block
                  // of instruction text.
                  <div className="space-y-2" role="status" aria-label="Loading instructions">
                    <Skeleton className="h-3 w-40" />
                    <Skeleton className="h-2.5 w-64" />
                    <Skeleton className="h-24" />
                  </div>
                ) : (
                  <p className="text-[11px] text-muted-foreground">Expand to load.</p>
                )
              ) : (
                reference.prompts
                  .filter((prompt) => prompt.stage === stage.stage)
                  .map((prompt) => (
                    <div key={prompt.id} className={cn("mb-5 last:mb-0", CONTENT_ARRIVAL_MOTION)}>
                      <p className="text-[11px] font-medium text-foreground">
                        {prompt.title}
                      </p>
                      {prompt.produces.ui_labels.length > 0 ? (
                        <p className="mt-1 text-[10px] font-medium text-foreground">
                          Behind the{" "}
                          {prompt.produces.ui_labels
                            .map((label) => SIGNAL_LABEL[label] ?? label)
                            .join(" and ")}{" "}
                          signal
                        </p>
                      ) : null}
                      <p className="mt-1 text-[10px] text-muted-foreground">
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
                  ))
              )}
            </div>
          </details>
        ))}
      </div>
    </div>
  );
}

// Stage order and framing follow the retrieval sequence a reader already met in
// the architecture diagram, so the two sections describe the same pipeline.
const STAGE_ORDER: { stage: string; title: string; description: string }[] = [
  {
    stage: "context_validator",
    title: "Indication check",
    description: "confirms the document matches the configured indication",
  },
  {
    stage: "unit_extractor",
    title: "Claim extraction",
    description: "pulls investigation units from a development plan",
  },
  {
    stage: "target_resolver",
    title: "Canonical claim resolution",
    description: "binds each field to its exact document language",
  },
  {
    stage: "conformity",
    title: "Quantitative mapping",
    description: "numeric targets, external measurements, reconciliation",
  },
  {
    stage: "target_reviewer",
    title: "Target review",
    description: "recommends which numeric proposals to keep",
  },
  {
    stage: "query_extractor",
    title: "Query planning",
    description: "general, geographic, counterfactual, precedent tracks",
  },
  {
    stage: "insight_extractor",
    title: "Insight extraction",
    description: "turns source findings into atomic facts",
  },
  {
    stage: "evidence_reviewer",
    title: "Measurement admission",
    description: "recommends which comparators enter statistics",
  },
  {
    stage: "drift_classifier",
    title: "Relationship classification",
    description: "contradicts, extends, confirms, unrelated",
  },
  {
    stage: "evidence_assessor",
    title: "Grounding assessment",
    description: "how well evidence justifies the document target",
  },
  {
    stage: "precedent_classifier",
    title: "Precedent coverage and outcome",
    description: "two separate signals, kept separate",
  },
  {
    stage: "projection_classifier",
    title: "Projection role",
    description: "classifies development landscape records",
  },
];
