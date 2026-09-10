"use client";

import { useState } from "react";
import { AlertTriangle, ChevronDown, Telescope } from "lucide-react";

import { ProvenancePanel } from "@/components/ui/provenance-panel";
import { Popover, PopoverTrigger } from "@/components/ui/popover";
import { InterfaceNote, Literal } from "@/components/ui/evidence-text";
import { ProvenanceTrigger, stopRowToggle } from "@/components/ui/provenance";
import type { ScoutResponse } from "@/lib/api";
import { DISCLOSURE_MOTION } from "@/lib/motion";
import { sourceDisplayLabel } from "@/lib/scout-labels";
import { fieldSearchRecord, searchRecordSummary, type SearchLaneGroup } from "@/lib/scout-search-record";
import { cn } from "@/lib/utils";

/**
 * What was searched for one field.
 *
 * The fourth direction of provenance, and the one that was missing. `In document` points at
 * the uploaded passage, `Sources` at the findings behind one insight, `Comparators` and
 * `Excluded` at a numeric cohort. None of them answers "how hard was this field looked at",
 * because all of them start from something that was found.
 *
 * `search_plan` already held the answer and was rendered nowhere: 754 traces on a real run,
 * of which `Sources` could show 229 of 529 distinct queries, because a search that returns
 * nothing produces no insight to hang it from. The 300 it could not show are the ones that
 * make a negative verdict readable, since "Unsupported" means opposite things depending on
 * whether a field was searched sixty ways or barely touched.
 *
 * It replaces a line that used to sit under the field reading "Searched by pulmonary TB
 * (disease)". That named an entity which, measured on a real run, appeared in 4 of the 62
 * searches for its field, so it claimed the aiming of a search it mostly did not aim.
 */
export function FieldSearches({
  result,
  attributeRef,
}: {
  result: Pick<ScoutResponse, "search_plan">;
  attributeRef: string;
}) {
  const [open, setOpen] = useState(false);
  const record = fieldSearchRecord(result, attributeRef);
  // A result saved before `search_plan` existed has nothing to show, and a trigger reading
  // zero would report an absence of searching rather than an absence of a record.
  if (record.total === 0) return null;

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button type="button" {...stopRowToggle}>
          <ProvenanceTrigger
            icon={Telescope}
            label="Searches"
            count={record.total}
            ariaLabel={`Searches: the ${record.total} search${record.total === 1 ? "" : "es"} planned for this field, and what each returned`}
          />
        </button>
      </PopoverTrigger>
      <ProvenancePanel
          onClose={() => setOpen(false)}
          eyebrow="Searches"
          title="What was looked for, and where"
          description={searchRecordSummary(record)}
      >
          <div>
            {record.groups.map((group) => (
              <LaneGroup key={group.lane} group={group} />
            ))}
          </div>
          {/* Once for the panel. A search returning nothing is the ordinary case here and
              saying so on each row would put the sentence sixty times on one field. */}
          <InterfaceNote className="mt-3">
            A search that returned nothing still ran. Sources beside an insight shows only the
            searches that found something, which is why they are listed here instead.
          </InterfaceNote>
      </ProvenancePanel>
    </Popover>
  );
}

/**
 * One lane, and every distinct query put to it.
 *
 * The same disclosure row as the groups inside a field: a chevron, a label, a count. The
 * trailing note is the exceptional case only, so a lane that ran and found things says
 * nothing beyond its count.
 */
function LaneGroup({ group }: { group: SearchLaneGroup }) {
  const skipped = group.searches.filter((trace) => trace.status === "skipped");
  const failed = group.searches.filter((trace) => trace.status === "failed");
  const note = skipped.length
    ? skipped.length === group.searches.length
      ? "not applicable to this field"
      : `${skipped.length} not applicable`
    : failed.length
      ? `${failed.length} failed`
      : group.findingCount === 0
        ? "nothing returned"
        : `${group.findingCount} source${group.findingCount === 1 ? "" : "s"}`;

  return (
    <details className="group/row">
      <summary className="flex cursor-pointer select-none flex-wrap items-center gap-x-2 gap-y-1 py-2 outline-none focus-visible:ring-2 focus-visible:ring-ring/20 [&::-webkit-details-marker]:hidden">
        <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground transition-transform group-open/row:rotate-180 motion-reduce:transition-none" />
        <span className="text-xs font-medium text-foreground">
          {sourceDisplayLabel(group.lane)}
        </span>
        <span className="text-[11px] tabular-nums text-muted-foreground">
          {group.searches.length}
        </span>
        <span className="text-[11px] text-muted-foreground">{note}</span>
      </summary>
      <ul className={cn("space-y-1.5 pb-2 pl-5", DISCLOSURE_MOTION)}>
        {group.searches.map((trace, index) => (
          <li key={`${trace.query}-${index}`}>
            {/* The query verbatim, in the monospace the app uses for a machine string.
                Nobody wrote it as a sentence, so it is shown character for character. */}
            <Literal className="block">{trace.query || "(no query text)"}</Literal>
            {/* Only when the search did not simply run and return. A reason on every row
                would be the same sentence sixty times. */}
            {trace.status === "skipped" && trace.applicability_reason && (
              <InterfaceNote variant="content" className="mt-1">{trace.applicability_reason}</InterfaceNote>
            )}
            {trace.status === "failed" && <div className="mt-1 flex items-start gap-2 text-[11px] leading-relaxed text-muted-foreground">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[hsl(var(--tone-warning))]" aria-hidden="true" />
              <span className="min-w-0 break-words">{trace.error || "This search failed."}</span>
            </div>}
          </li>
        ))}
      </ul>
    </details>
  );
}
