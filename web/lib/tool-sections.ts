import {
  EXTERNAL_TOOLS,
  WORKSPACE_TOOLS,
  type ToolDefinition,
} from "./tools.ts";

/**
 * How the landing page groups the catalog, and the order it presents each group in.
 *
 * Sections group by **audience** — who the tools belong to — and that is the only
 * axis they may use. A section grouped by anything else (a phase of the process, a
 * kind of analysis) puts two axes at one heading level, and a reader can no longer
 * tell what a heading is telling them. The kind of work a tool does is already
 * expressed per card, by its description, which is where a second axis belongs.
 *
 * Here rather than inside the page so the invariants can be tested: every id
 * resolves, every tool is placed exactly once, and no section reorders the tools
 * relative to the catalog. That last one is what keeps the landing page, the docs
 * tool list, and the Ask catalog from listing the same tools three ways - the
 * other two walk `WORKSPACE_TOOLS` and `EXTERNAL_TOOLS` directly and nothing sorts
 * them.
 */
export const ALL_TOOLS: readonly ToolDefinition[] = [
  ...WORKSPACE_TOOLS,
  ...EXTERNAL_TOOLS,
];

export type ToolSection = {
  id: string;
  toolIds: readonly ToolDefinition["id"][];
  title: string;
  description: string;
};

export const TOOL_SECTIONS: readonly ToolSection[] = [
  {
    id: "pst-workflows",
    // Reading order, not alphabetical: look up what has been required before, then
    // check a document, test what it claims, check the documents against each other,
    // and take them to the gate. Archivist is first because it is what you consult
    // before drafting, not a step in reviewing what you drafted.
    toolIds: ["archivist", "inspector", "scout", "aligner", "expert"],
    title: "PST team workflows",
    // The only place the cycle is stated. Each card states what its tool is judged
    // against; none of them repeats this. Keep the clauses in the same order as
    // `toolIds` above - the sentence is what the cards read as.
    description:
      "Look up what past profiles required, hold each document to its rubric, its targets to the evidence, and the documents to each other, then bundle for the gate.",
  },
  {
    id: "ghide-workflows",
    toolIds: [
      "ghide-evaluator",
      "ghide-roadmap-body-compiler",
      "ghide-executive-summary-compiler",
      "ghide-stage-gate-evaluator",
    ],
    title: "GHIDE team workflows",
    description:
      "Evaluate investments, prepare stage-gate decisions, and turn findings into leadership-ready outputs.",
  },
  {
    id: "shared-utilities",
    toolIds: ["chunker", "searcher"],
    // Not a subsection of the tools above, though every one of them parses through
    // Chunker and Scout searches through Searcher: these sit under those tools
    // rather than beside them, and nesting would read as a step in the sequence.
    // Named by audience like the two sections above, because that is the axis this file
    // groups on and both tools carry `audience: "shared"`. The description carries what
    // they are and when to reach for one, which is where a second axis belongs.
    title: "Shared utilities",
    description:
      "Every tool above parses through Chunker, and Scout searches through Searcher. Run either directly when you want the parsed blocks or the raw findings without an analysis around them.",
  },
];

/**
 * The tools of one section, in the order the section declares.
 *
 * Walks `toolIds` rather than filtering the catalog: the section owns its
 * presentation order, and filtering would silently fall back to definition order,
 * so editing `toolIds` would appear to do nothing.
 */
export function sectionTools(
  section: ToolSection,
  include: (tool: ToolDefinition) => boolean,
): ToolDefinition[] {
  return section.toolIds
    .map((id) => ALL_TOOLS.find((tool) => tool.id === id))
    .filter((tool): tool is ToolDefinition => tool != null && include(tool));
}
