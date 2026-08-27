export type ToolIcon =
  | "inspector"
  | "aligner"
  | "scout"
  | "expert"
  | "chunker"
  | "searcher"
  | "archivist"
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
   * Every workspace tool here renders a verdict, so every one names an authority. A
   * tool that judges nothing would have none to name and would state what it reports
   * and where that came from instead - do not invent an authority to make the
   * sentences match.
   */
  description: string;
  /* No `capability`. It was a two-word label - "Leadership summary", "Evidence review" - and
     in every case the description's own words, compressed. On a card it sat under that
     description; in the docs catalogue it was joined to it by a middot inside one sentence; and
     the assistant received it beside the description it repeated. Three consumers, one fact,
     said twice in each. */
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
    id: "archivist",
    href: "/archivist",
    title: "Archivist",
    // Imperative, like Chunker and Searcher, and for the reason the family rule gives:
    // this performs a lookup rather than judging a document. It names no authority
    // because it has none - the corpus is its authority, and a corpus is data.
    description:
      "Look up what past iTPPs and cTPPs required for an attribute, how many said nothing, and the quote behind each value.",
    // The floor of the shared scale rather than a truer word for it. There is no model
    // call on the read path - the corpus was built and reviewed in advance, so a query is
    // a filter over a few hundred committed rows - but these are read side by side, and
    // "instant" beside "approx. 20 min" is two scales rather than one comparison.
    activity: "approx. 1 min",
    icon: "archivist",
    // Owned by the PST team, who write these profiles, rather than shared: no other
    // tool reads the corpus, which is what makes Chunker and Searcher shared.
    audience: "pst",
    // The utility family by this file's own rule - it performs a task rather than
    // rendering a verdict - which is a different axis from who owns it.
    workflow: "utility",
    delivery: "workspace",
    availability: "available",
  },
  {
    id: "inspector",
    href: "/inspector",
    title: "Inspector",
    description:
      "One document against its rubric: what is missing, off-template, vague, or internally inconsistent.",
    activity: "approx. 1 min",
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
    activity: "approx. 20 min",
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
    // Same arithmetic as Expert's, one step longer: each comparison reads its
    // reference document once, then fans out over the requirements it found. Two
    // documents is one comparison; three is two, run in sequence.
    activity: "approx. 1 min",
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
    // Observed, not estimated. 80 questions at six concurrent is ~14 waves, and each
    // call returns one decision and one sentence — a few hundred bytes — against a
    // document context the provider caches after the first. The count of calls is not
    // what costs time here; the size of each answer is, and these are tiny.
    activity: "approx. 1 min",
    icon: "expert",
    audience: "pst",
    workflow: "stage_gate",
    delivery: "workspace",
    availability: "available",
  },
  {
    id: "chunker",
    href: "/chunker",
    title: "Chunker",
    description:
      "Turn DOCX and PPTX files into ordered, citable text, table, and image blocks.",
    activity: "approx. 1 min",
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
    activity: "approx. 5 min",
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
    icon: "stage-gate",
    audience: "ghide",
    workflow: "stage_gate",
    availability: "available",
    delivery: "external",
    // Claude only for now. The other GHIDE tools list both providers; this one
    // lists what exists rather than leaving a dead ChatGPT entry beside it.
    shortcuts: [
      {
        label: "Claude",
        url: "https://claude.ai/project/019f6bf2-9fa2-77f9-a6c3-01e29385fb64",
      },
    ],
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
