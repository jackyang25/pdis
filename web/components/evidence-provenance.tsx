"use client";

import { useState } from "react";
import { Globe, Search } from "lucide-react";
import { TracePanelHeader, TracePanelSection } from "@/components/document-trace-panel";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { ProvenanceTrigger, stopRowToggle } from "@/components/ui/provenance";
import { InterfaceNote, Literal, SourceEntry } from "@/components/ui/evidence-text";
import type { Finding, Insight } from "@/lib/api";
import { queryTrackLabel, sourceDisplayLabel } from "@/lib/scout-labels";

/**
 * Where one insight came from: its sources, and the searches that returned them.
 *
 * The outward half of provenance. `DocumentSourceTrace` is the inward half - the passage of
 * the *uploaded* document a finding was compared against - and the two were both reachable
 * from a button reading "View source", which named neither. They are now "In document" and
 * "Sources", which point in the two directions a reader actually distinguishes.
 *
 * Behind a click because the alternative was every source of every insight rendered the
 * moment a relation group opened: 1,121 finding rows on one run, most of them under
 * `extends`, all competing with the statements they support. The count is on the trigger, so
 * nothing is hidden - only deferred.
 *
 * Everything here is read off the saved result. `retrieval_paths` carries the exact query
 * and the lane that ran it, which is the one thing a reader cannot reconstruct: a finding
 * can look irrelevant until you see it was returned by a search for contrary evidence.
 */
export function EvidenceProvenance({ insight }: { insight: Insight }) {
  const [open, setOpen] = useState(false);
  const findings = insight.supporting_findings ?? [];
  if (findings.length === 0) return null;
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button type="button" {...stopRowToggle}>
          <ProvenanceTrigger
            icon={Globe}
            label="Sources"
            count={findings.length}
            ariaLabel={`Show the ${findings.length} source${findings.length === 1 ? "" : "s"} behind this insight and the searches that returned them`}
          />
        </button>
      </PopoverTrigger>
      <PopoverContent
        align="start"
        sideOffset={6}
        collisionPadding={12}
        className="w-[min(720px,calc(100vw-24px))] overflow-hidden p-0"
      >
        <TracePanelHeader
          eyebrow="Sources"
          title="What this insight rests on"
          description="Every source that carried this statement, and the search that returned each one."
        />
        <div className="max-h-[min(60vh,520px)] space-y-4 overflow-y-auto px-4 py-4">
          {/* Labelled, because this panel holds two kinds of thing. A panel with one kind
              needs no label; one with two needs both, or the unlabelled group reads as a
              preamble to the labelled one. */}
          <TracePanelSection label="Cited by this insight" className="border-t-0 pt-0">
            <ul className="mt-1.5">
              {findings.map((finding) => (
                <FindingProvenance key={finding.url} finding={finding} />
              ))}
            </ul>
          </TracePanelSection>
          {insight.query_tracks && insight.query_tracks.length > 0 && (
            <TracePanelSection label="How it was found" icon={Search}>
              {/* The track, not the query text: one of these exists to look for evidence
                  *against* a target, which is the difference between a finding that was
                  stumbled upon and one that was hunted for. Boxed, because this panel puts
                  the tool's account of a search directly beside a model's reading of what
                  the search returned. */}
              <InterfaceNote className="mt-1.5">
                Reached by {insight.query_tracks.map(queryTrackLabel).join(", ")}.
              </InterfaceNote>
            </TracePanelSection>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}

function FindingProvenance({ finding }: { finding: Finding }) {
  const lanes = Array.from(
    new Set(
      (finding.source_lanes?.length ? finding.source_lanes : [finding.source]).map((lane) =>
        sourceDisplayLabel(lane, finding.source_labels),
      ),
    ),
  );
  const date = finding.published_at
    ? new Date(finding.published_at).toLocaleDateString(undefined, {
        year: "numeric",
        month: "short",
      })
    : "date not stated";
  // One row per distinct query, not per retrieval path: the same query run against two
  // lanes is one search a reader recognises, and the raw list repeats it.
  const searches = Array.from(
    new Map(
      (finding.retrieval_paths ?? []).map((path) => [`${path.query}|${path.lane}`, path]),
    ).values(),
  );
  return (
    <SourceEntry
      title={finding.title || finding.url}
      href={finding.url}
      meta={[lanes.join(" + "), date].filter(Boolean).join(" · ")}
      // Verbatim, and trimmed with an ellipsis where long. A truncated quotation is still a
      // quotation; the ellipsis is what says so.
      quote={
        finding.excerpt
          ? finding.excerpt.length > 400
            ? `${finding.excerpt.slice(0, 400).trimEnd()}…`
            : finding.excerpt
          : undefined
      }
    >
      {searches.length > 0 && (
        <ul className="mt-1 space-y-0.5">
          {searches.map((path) => (
            <li
              key={`${path.query}|${path.lane}`}
              className="flex flex-wrap items-baseline gap-x-2 text-[11px] text-muted-foreground"
            >
              {lanes.length > 1 && (
                <span className="font-medium text-foreground">
                  {sourceDisplayLabel(path.lane, finding.source_labels)}
                </span>
              )}
              <Literal className="min-w-0">{path.query}</Literal>
              {path.connector && (
                <span>
                  via {path.connector}
                  {path.operation ? ` · ${path.operation}` : ""}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </SourceEntry>
  );
}
