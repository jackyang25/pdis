"use client";

import type { RequirementSnapshot, RubricResolution, RubricSnapshot, RubricSource } from "@/lib/api";
import { HelpHeading, HelpSection } from "@/components/ui/help-content";
import { DisclosureRow } from "@/components/ui/disclosure-row";
import { promptHref } from "@/lib/prompt-reference";

/** Authored requirements are presented identically for every authority and evidence mode. */
export function InspectorRequirement({ requirement, rubric }: { requirement: RequirementSnapshot; rubric: RubricSnapshot }) {
  return <div className="mt-2 text-xs text-muted-foreground"><DisclosureRow label="Rubric requirement">
    <div className="mt-2 max-w-prose space-y-2 leading-relaxed">
      <p>{requirement.description}</p>
      {requirement.expectations && <p>{requirement.expectations}</p>}
      <SourceLinks sources={rubric.sources.filter(source => requirement.source_refs.includes(source.id))} />
      {requirement.source_refs.length === 0 && <TemplateReference rubric={rubric} compact />}
    </div>
  </DisclosureRow></div>;
}

/** A template-level basis is not represented as a verified requirement-level citation. */
function TemplateReference({ rubric, compact = false }: { rubric: RubricSnapshot; compact?: boolean }) {
  if (!rubric.mirrors) return null;
  if (compact) return <p className="text-xs text-muted-foreground">
    Template basis: {rubric.reference_url
      ? <a href={rubric.reference_url} target="_blank" rel="noopener noreferrer"
          className="underline underline-offset-4 hover:text-foreground">Reference library</a>
      : <>{rubric.display_name}. Source details in rubric information.</>}
  </p>;
  return <div className="space-y-1 text-xs text-muted-foreground">
    <p><span className="font-medium">Template basis. </span>{rubric.mirrors}</p>
    {rubric.reference_url && <a href={rubric.reference_url} target="_blank" rel="noopener noreferrer"
      className="inline-block underline underline-offset-4 hover:text-foreground">Open reference library</a>}
    {rubric.reference_url?.startsWith("https://bmgf.sharepoint.com/") && <p>Foundation sign-in required.</p>}
  </div>;
}

function SourceLinks({ sources }: { sources: RubricSource[] }) {
  if (!sources.length) return null;
  return <ul className="space-y-1">
    {sources.map(source => <li key={source.id}>
      <a href={source.url} target="_blank" rel="noopener noreferrer" className="underline underline-offset-4 hover:text-foreground">{source.title}</a>
      <span> · {source.revision}</span>
    </li>)}
  </ul>;
}

export function InspectorRubricDetails({ rubric }: { rubric: RubricSnapshot }) {
  return <div className="space-y-4 text-xs leading-relaxed text-muted-foreground">
      <div className="space-y-2">
        <HelpHeading>{rubric.display_name}</HelpHeading>
        <p>{rubric.scope}</p>
      </div>
      <HelpSection title="Source and revision">
        <p>{rubric.authority}</p>
        <p>Rubric revision {rubric.revision ?? "not recorded"}</p>
        <TemplateReference rubric={rubric} />
        <SourceLinks sources={rubric.sources} />
      </HelpSection>
      <div className="space-y-2">
        <a href={promptHref("inspector", "assessment")} target="_blank" rel="noopener noreferrer"
          className="inline-block underline underline-offset-4 hover:text-foreground">View assessment instructions</a>
        <p>Authored document-review requirements, not certification of regulatory compliance.</p>
      </div>
  </div>;
}

/** Scope omissions remain visible; they are process facts, not optional help. */
export function InspectorRubricOmissions({ resolutions }: { resolutions: RubricResolution[] }) {
  const omitted = resolutions.filter(item => item.status !== "included");
  if (!omitted.length) return null;
  return <div className="space-y-2 text-xs text-muted-foreground" role="note" aria-label="Reviews not assessed">
    {omitted.map(item => <p key={item.rubric_id} className="max-w-prose leading-relaxed">
      <span className="font-medium text-foreground">{item.display_name} — {item.status === "needs_context" ? "Needs product context" : "Outside this review’s scope"}.</span> {item.reason}
    </p>)}
  </div>;
}
