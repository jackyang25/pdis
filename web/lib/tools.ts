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
   * What the tool reads, against the authority it is judged by, then what you
   * learn — one sentence, in that order.
   *
   * Inspector, Aligner, Expert, and Scout are told apart by their authority alone —
   * a rubric, the other documents, a gate's question bank, outside evidence — so
   * stating it in one shape is
   * what keeps their scopes legible. Never write what a tool does not do; if the
   * boundary is unclear, the positive statement is too vague.
   *
   * Four rules keep them comparable, because a card is read beside its siblings and
   * the differences between them are the whole point:
   *
   *   1. One sentence, 12-24 words. A longer card reads as a more important tool.
   *      Librarian sits at the top of the range because it is the only one whose
   *      source is access-controlled, and saying so is worth the words.
   *   2. Name artifacts by their acronym — iTPP, cTPP, IPDP. Long-form
   *      paraphrases make two cards about the same documents look like they are
   *      about different ones.
   *   3. The clause after the colon says what you learn, never what was searched.
   *   4. No domain examples. Naming vaccine attributes couples the copy to one of
   *      five intervention classes; what qualifies belongs in the attribute
   *      vocabulary.
   *
   * Utility and external tools are a separate family and use imperative voice
   * ("Turn DOCX and PPTX files into…"), because they perform a task rather than
   * judge a document. Keep each family internally consistent.
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
 *
 * Librarian trails those four although its question comes before all of them,
 * because leading with it pushes Scout off the first row of the landing page's
 * two-column grid.
 */
export const WORKSPACE_TOOLS: readonly WorkspaceToolDefinition[] = [
  {
    id: "inspector",
    href: "/inspector",
    title: "Inspector",
    description:
      "One document against its rubric: what is missing, off-template, vague, or internally inconsistent.",
    capability: "Document review",
    activity: "~1 min",
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
      "One document’s targets against external evidence: whether its numbers hold up against comparable measurements and precedent.",
    capability: "Evidence review",
    activity: "~15 min",
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
      "The iTPP, cTPP, and IPDP against each other: whether the candidate and the plan deliver what was asked for.",
    capability: "Document comparison",
    // Same arithmetic as Expert's, one step longer: each comparison reads its
    // reference document once, then fans out over the requirements it found. Two
    // documents is one comparison; three is two, run in sequence.
    activity: "~1 min",
    icon: "aligner",
    audience: "pst",
    workflow: "document_intelligence",
    delivery: "workspace",
    availability: "available",
  },
  {
    id: "expert",
    href: "/expert",
    title: "Expert",
    description:
      "The iTPP, cTPP, and IPDP against the stage-gate criteria: what is still unresolved, and which reviewer it goes to.",
    capability: "Stage-gate preparation",
    // Observed, not estimated. 80 questions at six concurrent is ~14 waves, and each
    // call returns one decision and one sentence — a few hundred bytes — against a
    // document context the provider caches after the first. The count of calls is not
    // what costs time here; the size of each answer is, and these are tiny.
    activity: "~1 min",
    icon: "expert",
    audience: "pst",
    workflow: "stage_gate",
    delivery: "workspace",
    availability: "available",
  },
  {
    id: "librarian",
    title: "Librarian",
    // No authority clause, because this tool judges nothing. See the note on
    // `description` above: the others name what they are judged against, and
    // giving this one an authority to match would make it Aligner with a corpus.
    // "Indication-independent", not "pathogen-independent": a pathogen is the
    // vaccine-shaped instance of the general rule, and the config also carries
    // drugs, mabs, diagnostics, and devices, whose indication may name no pathogen
    // at all. No attribute examples for the same reason - dosing and duration of
    // protection are vaccine-shaped, and which attributes qualify belongs to the
    // attribute vocabulary rather than to this sentence.
    description:
      "The iTPPs, cTPPs, and IPDPs you are permitted to view, without uploading one: what comparable programs committed to on attributes independent of the indication.",
    capability: "Library reference",
    icon: "librarian",
    audience: "pst",
    workflow: "document_intelligence",
    delivery: "workspace",
    // Nothing is built. The card exists so the gap it fills is visible next to the
    // tools that cannot fill it: Inspector, Aligner, Expert, and Scout all need a
    // document that already states something, and drafting from scratch has none.
    availability: "coming_soon",
  },
  {
    id: "chunker",
    href: "/chunker",
    title: "Chunker",
    description:
      "Turn DOCX and PPTX files into ordered, citable text, table, and image blocks.",
    capability: "Document parsing",
    activity: "~1 min",
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
    activity: "~5 min",
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

/**
 * A tool's own sentence: what it reads, and the authority it judges against.
 *
 * The catalog description is that sentence — every tool's was rewritten to that shape —
 * so anything needing to state a tool's authority reads it from here rather than writing
 * a second version that could disagree.
 */
export function toolAuthority(id: string): string {
  return WORKSPACE_TOOLS.find((tool) => tool.id === id)?.description ?? "";
}

export function toolForPath(pathname: string | null) {
  return WORKSPACE_TOOLS.find(
    (tool) => tool.href
      && (pathname === tool.href || pathname?.startsWith(`${tool.href}/`)),
  );
}
