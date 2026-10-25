"use client";

import { ReportFinding } from "@/components/report-finding";
import { DisclosureRow } from "@/components/ui/disclosure-row";
import { Computed, InterfaceNote, Quoted, Reading, SourceEntry } from "@/components/ui/evidence-text";
import type { DraftBasis, DraftVariable } from "@/lib/api";
import { displayAttributeLabel } from "@/lib/scout-labels";
import { ROW_TITLE } from "@/lib/typography";
import { cn } from "@/lib/utils";
import {
  DRAFTER_PANELS,
  evidenceSources,
  figureLine,
  panelOf,
  suggestionLines,
  type EvidenceSource,
} from "@/lib/drafter-presentation";
import { countLabel } from "@/lib/count-label";

const BASIS_LABEL: Record<DraftBasis, string> = {
  comparable_product: "Comparable products",
  published_guidance: "Published guidance",
};

/**
 * One iTPP variable: the target the run suggests, why, and the evidence behind it.
 *
 * The two kinds of evidence are separate lists, never one: what comparable products
 * achieved and what guidance asks are different claims, and a suggestion says which it
 * leans on. Nothing here is decided in PDIS; the team edits the exported table.
 */
export function DrafterVariableRow({ variable }: { variable: DraftVariable }) {
  const panel = panelOf(variable);
  const { suggestion } = variable;
  const target = panel === "suggested" && suggestion ? suggestionLines(suggestion).join(" · ") : "";
  return (
    <li className="group/variable min-w-0 py-4 first:pt-0 last:pb-0">
      <div className="flex items-start justify-between gap-3">
        <span className={cn("min-w-0 break-words", ROW_TITLE)}>
          {/* The shared variable name, so this row and Scout's field read the same. */}
          {displayAttributeLabel(variable.name)}
        </span>
        {/* Beside the name and revealed on hover or focus: thirty rows each carrying a visible
            action was a column of noise for something a reader does rarely, and a hidden one on
            its own line left a blank band under every row. Always shown where there is no hover. */}
        <div className="-my-1 shrink-0 transition-opacity duration-base motion-reduce:transition-none sm:opacity-0 sm:group-hover/variable:opacity-100 sm:group-focus-within/variable:opacity-100">
          <ReportFinding
            className="-mr-2.5 ml-0"
            report={{
              finding: `${DRAFTER_PANELS.find((entry) => entry.id === panel)?.title}: ${displayAttributeLabel(variable.name)}`,
              detail: [target, suggestion?.rationale].filter(Boolean).join(" · "),
              reference: variable.name,
              location: countLabel(variable.observations.length, "observation"),
            }}
          />
        </div>
      </div>

      {/* The target and its rationale are one contribution, so the second hangs off the first
          rather than carrying a second mark. */}
      {target && <Reading size="prominent">{target}</Reading>}
      {suggestion?.rationale && <Reading continued={Boolean(target)}>{suggestion.rationale}</Reading>}
      {/* The tool's own note, and only when nothing was retrieved or read: with sources set
          aside, or a model's empty rationale over evidence, it would not be true. */}
      {panel === "insufficient" && !suggestion?.rationale && variable.observations.length === 0 && variable.unread_findings === 0 && variable.unverified_quotes === 0 && (
        <InterfaceNote variant="content" className="mt-1">No source this run found spoke to this variable.</InterfaceNote>
      )}
      {panel === "failed" && variable.failure && (
        <InterfaceNote variant="content" className="mt-1">{variable.failure.message}</InterfaceNote>
      )}

      {variable.statistics.map((group) => (
        <Computed key={group.unit} className="mt-1.5 block text-[11px] text-muted-foreground">
          {figureLine(group)}
        </Computed>
      ))}

      {(variable.observations.length > 0 || variable.unread_findings > 0 || variable.unverified_quotes > 0) && (
        <div className="mt-2">
          {(["comparable_product", "published_guidance"] as const).map((basis) => (
            <EvidenceList key={basis} basis={basis} sources={evidenceSources(variable, basis)} />
          ))}
          {variable.unread_findings > 0 && (
            <p className="py-1.5 text-[11px] text-muted-foreground">
              {countLabel(variable.unread_findings, "source")} could not be read
              and {variable.unread_findings === 1 ? "was" : "were"} set aside.
            </p>
          )}
          {variable.unverified_quotes > 0 && (
            <p className="py-1.5 text-[11px] text-muted-foreground">
              {countLabel(variable.unverified_quotes, "quote")} could not be found in{" "}
              {variable.unverified_quotes === 1 ? "its source" : "their source"}
              {" "}and {variable.unverified_quotes === 1 ? "was" : "were"} set aside.
            </p>
          )}
        </div>
      )}
    </li>
  );
}

function EvidenceList({ basis, sources }: { basis: DraftBasis; sources: EvidenceSource[] }) {
  if (sources.length === 0) return null;
  return (
    <DisclosureRow label={BASIS_LABEL[basis]} count={sources.length}>
      <ul className="pt-1">
        {sources.map((source) => <EvidenceEntry key={source.url} source={source} />)}
      </ul>
    </DisclosureRow>
  );
}

/** One source, once, with each thing it said: the `SourceEntry` shape with its quotes beneath. */
function EvidenceEntry({ source }: { source: EvidenceSource }) {
  return (
    <SourceEntry
      title={source.title || source.url}
      href={source.url}
      meta={[source.source_label, source.published, source.cited ? "Cited by the suggestion" : ""].filter(Boolean).join(" · ")}
    >
      {source.passages.map((passage) => {
        const detail = [passage.products.join(", "), passage.figure].filter(Boolean).join(" · ");
        return (
          <div key={`${passage.quote}|${passage.figure}`} className="mt-2">
            {detail && <Computed className="block text-[11px] leading-relaxed">{detail}</Computed>}
            <Quoted collapsible>{passage.quote}</Quoted>
          </div>
        );
      })}
    </SourceEntry>
  );
}
