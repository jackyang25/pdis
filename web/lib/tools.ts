export type ToolIcon =
  | "inspector"
  | "scout"
  | "chunker"
  | "searcher"
  | "evaluator"
  | "roadmap"
  | "executive-summary";

type ToolBase = {
  id: string;
  title: string;
  description: string;
  capability: string;
  icon: ToolIcon;
};

export type WorkspaceToolDefinition = ToolBase & {
  delivery: "workspace";
  area: "document_intelligence" | "utility";
  href: string;
  activity: string;
};

export type ExternalToolDefinition = ToolBase & {
  delivery: "external";
  shortcuts: readonly {
    label: "ChatGPT" | "Claude";
    url: string;
  }[];
  sequence: number;
};

export type ToolDefinition = WorkspaceToolDefinition | ExternalToolDefinition;

/** Native tools run inside PDIS and may own workspace configuration. */
export const WORKSPACE_TOOLS: readonly WorkspaceToolDefinition[] = [
  {
    id: "inspector",
    href: "/inspector",
    title: "Inspector",
    description:
      "Check whether a document meets its required rubric for completeness, adherence, rigor, and internal consistency.",
    capability: "Document quality",
    activity: "3–5 min",
    icon: "inspector",
    delivery: "workspace",
    area: "document_intelligence",
  },
  {
    id: "scout",
    href: "/scout",
    title: "Scout",
    description:
      "Test document targets against external evidence, quantitative alignment, and development precedent.",
    capability: "Evidence diligence",
    activity: "25–30 min",
    icon: "scout",
    delivery: "workspace",
    area: "document_intelligence",
  },
  {
    id: "chunker",
    href: "/chunker",
    title: "Chunker",
    description:
      "Parse DOCX, PDF, and PPTX files into ordered, citable text, table, and image blocks.",
    capability: "Document processing",
    activity: "On demand",
    icon: "chunker",
    delivery: "workspace",
    area: "utility",
  },
  {
    id: "searcher",
    href: "/searcher",
    title: "Searcher",
    description:
      "Run a free-text query across selected evidence sources and return normalized findings.",
    capability: "Evidence retrieval",
    activity: "On demand",
    icon: "searcher",
    delivery: "workspace",
    area: "utility",
  },
] as const;

/**
 * Existing GHIDE tools, paired by workflow position across ChatGPT and Claude.
 */
export const EXTERNAL_TOOLS: readonly ExternalToolDefinition[] = [
  {
    id: "ghide-evaluator",
    title: "GHIDE Evaluator",
    description:
      "Assess a development plan for funding decision-readiness, surfacing program risks, evidence gaps, and recommended actions.",
    capability: "Investment evaluation",
    icon: "evaluator",
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
    sequence: 1,
  },
  {
    id: "ghide-roadmap-body-compiler",
    title: "GHIDE Roadmap Body Compiler",
    description:
      "Turn evaluator findings and expert feedback into a structured roadmap of organized recommendations and actions.",
    capability: "Roadmap synthesis",
    icon: "roadmap",
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
    sequence: 2,
  },
  {
    id: "ghide-executive-summary-compiler",
    title: "GHIDE Executive Summary Compiler",
    description:
      "Condense the completed roadmap into a one-page summary of priorities, decisions, and actions for leadership.",
    capability: "Executive synthesis",
    icon: "executive-summary",
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
    sequence: 3,
  },
] as const;

export function toolForPath(pathname: string | null) {
  return WORKSPACE_TOOLS.find(
    (tool) => pathname === tool.href || pathname?.startsWith(`${tool.href}/`),
  );
}
