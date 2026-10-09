/**
 * The one shape every tool's result is read through for its priority card.
 *
 * A tool does not choose its priorities here. It says which findings its result holds, named
 * the way its own page names them, and one sentence about what its reader needs first; a
 * model reads all of them and returns points that name findings by ID. The card then shows
 * each point's findings from this list, so a point can never describe a finding differently
 * from the row it points at — which is what the hand-written selectors this replaced kept
 * doing, each rebuilding names and quotes the page already rendered.
 */

import type { PriorityReadingRequest } from "./api.ts";

/** One thing the result judged, as the tool's own page names it. */
export type PriorityFinding = {
  /** Unique within the result, and the ID the result itself carries. */
  id: string;
  /** What it is about: a rubric unit, a requirement, a field, a question. */
  subject: string;
  /** Where it sits in the tool's own structure: a section, a comparison, a discipline. */
  group?: string;
  /** The tool's verdicts on it, in the labels its page shows. Assigned by code. */
  verdicts: string[];
  /** Sentences the tool's model wrote about it. */
  statements: string[];
  /**
   * Facts code derived about it - Aligner's note that an earlier comparison flagged the
   * same passage. Kept apart from `statements` so nothing code wrote is read as a model's.
   */
  notes?: string[];
  /** The document's own words, where the finding is about something the document states. */
  quote?: string;
  /** Passages it cites, for the card's source trigger. Never sent to the model. */
  blockIds: string[];
};

/** What a tool hands its card. Everything that differs between tools is in here. */
export type PriorityLens = {
  /** The tool's catalog sentence: what it reads, and the authority it judges against. */
  authority: string;
  /** One sentence: what this tool's reader needs first. */
  focus: string;
  findings: PriorityFinding[];
  org: string;
  interventionClass: string;
  indication: string;
};

/** The request the card sends. Block IDs stay behind: the model points at findings. */
export function priorityRequest(lens: PriorityLens): PriorityReadingRequest {
  return {
    authority: lens.authority,
    focus: lens.focus,
    findings: lens.findings.map((finding) => ({
      id: finding.id,
      subject: finding.subject,
      group: finding.group ?? "",
      verdicts: finding.verdicts,
      statements: finding.statements.filter(Boolean),
      notes: finding.notes ?? [],
      quote: finding.quote ?? "",
    })),
    org: lens.org,
    intervention_class: lens.interventionClass,
    indication: lens.indication,
  };
}
