import {
  EXTERNAL_TOOLS,
  WORKSPACE_TOOLS,
  type ToolDefinition,
} from "./tools.ts";

/**
 * How the landing page groups the catalog, and the order it presents each group in.
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
    // check the documents against each other, then take them to the gate. In the
    // two-column grid this puts the two per-document tools on the first row.
    toolIds: ["inspector", "scout", "aligner", "expert"],
    title: "PST team workflows",
    // The only place the between-gates cycle is stated. Each card states what its
    // tool is judged against; none of them repeats this. Keep the three clauses in
    // the same order as `toolIds` above - the sentence is what the cards read as.
    description:
      "Between stage gates these documents drift apart. Keep each one true to its rubric, its targets true to the evidence, and the documents true to each other — then bundle for the next gate.",
  },
  {
    id: "drafting",
    toolIds: ["librarian"],
    title: "Drafting from precedent",
    // Its own group rather than a fifth card in the band above, for two reasons: a
    // fifth card would push Scout out of the first row, and this is a different
    // moment in the process - before the first profile exists, when there is
    // nothing yet to check, compare, or test.
    description:
      "Before the first profile exists there is nothing to check against. Read what comparable programs have already asked for.",
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
    title: "Shared utilities",
    description:
      "Work directly with parsed document content or registered evidence sources.",
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
