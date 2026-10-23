"use client";

import { DisclosureSummary } from "@/components/ui/disclosure-summary";
import { Computed, InterfaceNote, Reading, SourceEntry } from "@/components/ui/evidence-text";
import type { DraftBasis, DraftObservation, DraftVariable } from "@/lib/api";
import { figureLine, panelOf, suggestionLines } from "@/lib/drafter-presentation";

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
  return (
    <li className="min-w-0 py-3 first:pt-0 last:pb-0">
      <span className="block min-w-0 break-words text-xs font-medium leading-relaxed text-foreground">
        {variable.label}
      </span>
      {variable.description && (
        <p className="mt-0.5 line-clamp-2 text-[11px] leading-relaxed text-muted-foreground">{variable.description}</p>
      )}

      {panel === "suggested" && suggestion && (
        <Reading size="prominent" className="mt-2">{suggestionLines(suggestion).join(" · ")}</Reading>
      )}
      {suggestion?.rationale && <Reading className="mt-1.5">{suggestion.rationale}</Reading>}
      {/* The tool's own note, and only when nothing was retrieved or read: with sources set
          aside, or a model's empty rationale over evidence, it would not be true. */}
      {panel === "insufficient" && !suggestion?.rationale && variable.observations.length === 0 && variable.unread_findings === 0 && (
        <InterfaceNote className="mt-1.5">No source this run found spoke to this variable.</InterfaceNote>
      )}
      {panel === "failed" && variable.failure && (
        <InterfaceNote className="mt-1.5">{variable.failure.message}</InterfaceNote>
      )}

      {variable.statistics.map((group) => (
        <Computed key={group.unit} className="mt-1.5 block text-[11px] text-muted-foreground">
          {figureLine(group)}
        </Computed>
      ))}

      <EvidenceLists variable={variable} />
      {variable.unread_findings > 0 && (
        <InterfaceNote className="mt-1.5">
          {variable.unread_findings} {variable.unread_findings === 1 ? "source" : "sources"} could not be read and{" "}
          {variable.unread_findings === 1 ? "was" : "were"} set aside.
        </InterfaceNote>
      )}
    </li>
  );
}

function EvidenceLists({ variable }: { variable: DraftVariable }) {
  const cited = new Set(variable.suggestion?.basis_ids ?? []);
  return (
    <>
      {(["comparable_product", "published_guidance"] as const).map((basis) => {
        const observations = variable.observations
          .filter((observation) => observation.basis === basis)
          // What the suggestion rests on first, so the reader checks those before the rest.
          .sort((a, b) => Number(cited.has(b.id)) - Number(cited.has(a.id)));
        if (observations.length === 0) return null;
        return (
          <details key={basis} className="mt-1.5">
            <DisclosureSummary className="w-fit select-none rounded-sm text-[11px] font-medium text-muted-foreground outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/20">
              {BASIS_LABEL[basis]} {observations.length}
            </DisclosureSummary>
            <ul className="mt-2">
              {observations.map((observation) => (
                <ObservationEntry key={observation.id} observation={observation} cited={cited.has(observation.id)} />
              ))}
            </ul>
          </details>
        );
      })}
    </>
  );
}

function ObservationEntry({ observation, cited }: { observation: DraftObservation; cited: boolean }) {
  const value = observation.value;
  const figure = value
    ? [value.value != null ? `${value.value}` : "", value.lower != null && value.upper != null ? `${value.lower}–${value.upper}` : ""]
        .filter(Boolean).join(" ") + (value.unit ? ` ${value.unit}` : "")
    : "";
  const meta = [observation.product, observation.source_label, figure].filter(Boolean).join(" · ");
  return (
    <SourceEntry title={observation.title || observation.url} href={observation.url} meta={meta} quote={observation.quote}>
      {cited && <InterfaceNote className="mt-1">Cited by this suggestion.</InterfaceNote>}
    </SourceEntry>
  );
}
