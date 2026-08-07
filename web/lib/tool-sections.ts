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
 * expressed per card, in `capability`, which is where a second axis belongs.
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
  /** Renders shorter cards, which reads as a footer band rather than a peer group. */
  compact?: boolean;
};

export const TOOL_SECTIONS: readonly ToolSection[] = [
  {
    id: "pst-workflows",
    // Reading order, not alphabetical: check a document, test what it claims, then
    // check the documents against each other, then take them to the gate. Librarian
    // trails because it answers the question that comes before all of them, and
    // leading with it would push Scout off the first row of the two-column grid.
    toolIds: ["inspector", "scout", "aligner", "expert", "librarian"],
    title: "PST team workflows",
    // The only place the cycle is stated. Each card states what its tool is judged
    // against; none of them repeats this. Keep the clauses in the same order as
    // `toolIds` above - the sentence is what the cards read as.
    description:
      "Between stage gates these documents drift apart. Keep each one true to its rubric, its targets true to the evidence, and the documents true to each other — then bundle for the next gate. When there is no profile yet, read what comparable programs asked for.",
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
    id: "building-blocks",
    toolIds: ["chunker", "searcher"],
    // Not a subsection of the tools above, though every one of them parses through
    // Chunker and Scout searches through Searcher: these sit under those tools
    // rather than beside them, and nesting would read as a step in the sequence.
    title: "Building blocks",
    description:
      "The parsing and retrieval layers the tools above are built on, usable directly.",
    compact: true,
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
