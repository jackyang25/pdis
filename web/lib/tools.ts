export type ToolIcon =
  | "inspector"
  | "aligner"
  | "scout"
  | "expert"
  | "librarian"
  | "chunker"
  | "searcher"
  | "evaluator"
  | "roadmap"
  | "executive-summary"
  | "stage-gate";

export type ToolAudience = "pst" | "ghide" | "shared";
export type ToolWorkflow =
  | "document_intelligence"
  | "stage_gate"
  | "decision_workflow"
  | "utility";

type ToolBase = {
  id: string;
  title: string;
  /**
   * What the tool reads, against the authority it is judged by, in that order.
   *
   * Inspector, Aligner, and Scout are told apart by their authority alone — a
   * rubric, the other documents, outside evidence — so stating it in one shape is
   * what keeps their scopes legible. Never write what a tool does not do; if the
   * boundary is unclear, the positive statement is too vague.
   *
   * Where these sit in a PPL's process is said once, in the section copy in
   * `lib/tool-sections.ts`, not here.
   *
   * A tool that renders no verdict has no authority to name, so it states what it
   * reports and where that came from instead. Librarian is the only one; do not
   * give it an authority to make the sentences match.
   */
  description: string;
  capability: string;
  icon: ToolIcon;
  audience: ToolAudience;
  workflow: ToolWorkflow;
  availability: "available" | "coming_soon";
};

export type WorkspaceToolDefinition = ToolBase & {
  delivery: "workspace";
  href?: string;
  activity?: string;
};

export type ExternalToolDefinition = ToolBase & {
  delivery: "external";
  shortcuts: readonly {
    label: "ChatGPT" | "Claude";
    url: string;
  }[];
};

export type ToolDefinition = WorkspaceToolDefinition | ExternalToolDefinition;

/**
 * Native tools run inside PDIS and may own workspace configuration.
 *
 * Declared in the order a PPL uses them — check a document, test what it claims,
 * check the documents against each other, take them to the gate — because the
 * docs page and the Ask catalog both present them in this order and nothing sorts
 * them. The landing page states the same order in its own `toolIds`; keep the two
 * agreeing so one surface never lists the tools differently from another.
 */
export const WORKSPACE_TOOLS: readonly WorkspaceToolDefinition[] = [
  {
    id: "inspector",
    href: "/inspector",
    title: "Inspector",
    description:
      "One document against its rubric: what is missing, off-template, vague, or internally inconsistent.",
    capability: "Document review",
    activity: "3–5 min",
    icon: "inspector",
    audience: "pst",
    workflow: "document_intelligence",
    delivery: "workspace",
    availability: "available",
  },
  {
    id: "scout",
    href: "/scout",
    title: "Scout",
    description:
      "One document’s targets against external evidence: comparable measurements and development precedent.",
    capability: "Evidence review",
    activity: "25–30 min",
    icon: "scout",
    audience: "pst",
    workflow: "document_intelligence",
    delivery: "workspace",
    availability: "available",
  },
  {
    id: "aligner",
    href: "/aligner",
    title: "Aligner",
    description:
      "The intervention profile, candidate profile, and development plan against each other: where the candidate and the plan diverge from what was asked for.",
    capability: "Document comparison",
    activity: "10–15 min",
    icon: "aligner",
    audience: "pst",
    workflow: "document_intelligence",
    delivery: "workspace",
    // The input layer is built and the page runs, but no comparison is reported
    // yet. `href` stays so the route remains reachable for development; the card
    // renders unlinked until this flips back to `available`.
    availability: "coming_soon",
  },
  {
    id: "expert",
    title: "Expert",
    description:
      "The documents against the stage-gate criteria: what is still unresolved, and which expert reviewer it goes to.",
    capability: "Stage-gate preparation",
    icon: "expert",
    audience: "pst",
    workflow: "stage_gate",
    delivery: "workspace",
    availability: "coming_soon",
  },
  {
    id: "librarian",
    title: "Librarian",
    // No authority clause, because this tool judges nothing. See the note on
    // `description` above: the others name what they are judged against, and
    // giving this one an authority to match would make it Aligner with a corpus.
    description:
      "What comparable programs committed to on pathogen-independent attributes — dosing, protection, presentation, shelf life, price — read from the iTPPs, cTPPs, and IPDPs you are permitted to view. Nothing is uploaded; every value cites its source.",
    capability: "Library reference",
    icon: "librarian",
    audience: "pst",
    workflow: "document_intelligence",
    delivery: "workspace",
    // Nothing is built. The card exists so the gap it fills is visible next to the
    // tools that cannot fill it: Inspector, Aligner, and Scout all need a document
    // that already states something, and drafting from scratch has none.
    availability: "coming_soon",
  },
  {
    id: "chunker",
    href: "/chunker",
    title: "Chunker",
    description:
      "Turn DOCX and PPTX files into ordered, citable text, table, and image blocks.",
    capability: "Document parsing",
    activity: "On demand",
    icon: "chunker",
    audience: "shared",
    workflow: "utility",
    delivery: "workspace",
    availability: "available",
  },
  {
    id: "searcher",
    href: "/searcher",
    title: "Searcher",
    description:
      "Search selected evidence sources directly and review normalized findings in one place.",
    capability: "Direct search",
    activity: "On demand",
    icon: "searcher",
    audience: "shared",
    workflow: "utility",
    delivery: "workspace",
    availability: "available",
  },
] as const;

/**
 * Existing GHIDE tools, exposed through their ChatGPT and Claude entry points.
 */
export const EXTERNAL_TOOLS: readonly ExternalToolDefinition[] = [
  {
    id: "ghide-evaluator",
    title: "GHIDE Evaluator",
    description:
      "Evaluate a development plan for funding readiness and identify program risks, evidence gaps, and next actions.",
    capability: "Funding readiness",
    icon: "evaluator",
    audience: "ghide",
    workflow: "decision_workflow",
    availability: "available",
    delivery: "external",
    shortcuts: [
      {
        label: "ChatGPT",
        url: "https://chatgpt.com/g/g-68507d1571548191840793cac22ba724-ghide-evaluator",
      },
      {
        label: "Claude",
        url: "https://claude.ai/project/019cb543-8867-73f2-b9f6-3f08435bdfa7",
      },
    ],
  },
  {
    id: "ghide-roadmap-body-compiler",
    title: "GHIDE Roadmap Body Compiler",
    description:
      "Turn evaluation findings and expert feedback into an organized roadmap of recommendations and actions.",
    capability: "Roadmap development",
    icon: "roadmap",
    audience: "ghide",
    workflow: "decision_workflow",
    availability: "available",
    delivery: "external",
    shortcuts: [
      {
        label: "ChatGPT",
        url: "https://chatgpt.com/g/g-699df6038e748191b86b11e096ca7b9b-ghide-roadmap-body-compiler",
      },
      {
        label: "Claude",
        url: "https://claude.ai/project/019cdef8-cdd4-75f9-ae2d-ec416afcb1d1",
      },
    ],
  },
  {
    id: "ghide-executive-summary-compiler",
    title: "GHIDE Executive Summary Compiler",
    description:
      "Turn a completed roadmap into a one-page leadership summary of priorities, decisions, and actions.",
    capability: "Leadership summary",
    icon: "executive-summary",
    audience: "ghide",
    workflow: "decision_workflow",
    availability: "available",
    delivery: "external",
    shortcuts: [
      {
        label: "ChatGPT",
        url: "https://chatgpt.com/g/g-699e3e9f92448191b723de6b25d158c7-ghide-exec-summary-writer",
      },
      {
        label: "Claude",
        url: "https://claude.ai/project/019dd549-2ab4-77ef-b1b5-318d98b93431",
      },
    ],
  },
  {
    id: "ghide-stage-gate-evaluator",
    title: "GHIDE Stage Gate Evaluator",
    description:
      "Evaluate whether a grantee has met stage-gate criteria and identify what is needed to reach the next gate.",
    capability: "Stage-gate evaluation",
    icon: "stage-gate",
    audience: "ghide",
    workflow: "stage_gate",
    availability: "coming_soon",
    delivery: "external",
    shortcuts: [],
  },
] as const;

export function toolForPath(pathname: string | null) {
  return WORKSPACE_TOOLS.find(
    (tool) => tool.href
      && (pathname === tool.href || pathname?.startsWith(`${tool.href}/`)),
  );
}
