export type ToolIcon =
  | "inspector"
  | "aligner"
  | "scout"
  | "screener"
  | "chunker"
  | "searcher";

export type ToolAudience = "pst" | "shared";
export type ToolWorkflow =
  | "document_intelligence"
  | "stage_gate"
  | "utility";

type ToolBase = {
  id: string;
  title: string;
  /**
   * What the tool reads, against the authority it is judged by, then what you
   * learn — one sentence, in that order.
   *
   * Inspector, Aligner, Screener, and Scout are told apart by their authority alone —
   * a rubric, the other documents, a stage gate's question bank, outside evidence — so
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
   * Utility tools are a separate family and use imperative voice ("Turn DOCX and
   * PPTX files into…"), because they perform a task rather than judge a document.
   * Keep each family internally consistent.
   *
   * Where these sit in a PPL's process is said once, in the section copy in
   * `lib/tool-sections.ts`, not here.
   *
   * Every workspace tool here renders a verdict, so every one names an authority. A
   * tool that judges nothing would have none to name and would state what it reports
   * and where that came from instead - do not invent an authority to make the
   * sentences match.
   */
  /**
   * What this tool judges, against what, and what it is not.
   *
   * One grammar for all four, because a reader choosing between them is comparing:
   * `<what is judged> against <the authority>: <what you learn>. <Territory>, not
   * <the neighbour's territory>.`
   *
   * One grammar for every tool that reads documents:
   *
   *     <what is read>  against  <the authority>:  <what you learn>
   *
   * Chunker and Searcher are outside it. They are operations rather than readings -
   * they turn a file into blocks, or run a query - so they have no authority to name
   * and their imperative grammar is correct for what they are.
   *
   * A card states what the tool judges and against what. The boundary clause - which
   * territory it owns and which it leaves to a neighbour - lives on the tool's own page,
   * where a reader who has chosen it has room to read it. On a catalogue of six, six
   * boundary clauses is a second sentence on every card for a distinction that only
   * matters once you are about to run one.
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
  href?: string;
  activity?: string;
};

/** Every tool runs inside PDIS; the catalog lists nothing that opens elsewhere. */
export type ToolDefinition = WorkspaceToolDefinition;

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
      "An iTPP, cTPP, or IPDP against its authored rubrics: what the document specifies and what each requirement leaves unresolved.",
    activity: "1 minute",
    icon: "inspector",
    audience: "pst",
    workflow: "document_intelligence",
    availability: "available",
  },
  {
    id: "scout",
    href: "/scout",
    title: "Scout",
    description:
      "One document’s targets against external evidence: whether its numbers hold up against comparable measurements and development precedent.",
    activity: "20 minutes",
    icon: "scout",
    audience: "pst",
    workflow: "document_intelligence",
    availability: "available",
  },
  {
    id: "aligner",
    href: "/aligner",
    title: "Aligner",
    description:
      "The iTPP, cTPP, and IPDP against each other: whether each honours the one before it, requirement by requirement.",
    // Each comparison reads its reference document once, then fans out over
    // the requirements it found. Two
    // documents is one comparison; three is two, run in sequence.
    activity: "1 minute",
    icon: "aligner",
    audience: "pst",
    workflow: "document_intelligence",
    availability: "available",
  },
  {
    id: "screener",
    href: "/screener",
    title: "Screener",
    description:
      "Your documents against a stage gate’s question bank: what is answered, what remains open, and which discipline owns each question.",
    // Observed end-to-end estimate, including document processing and assessment.
    // Actual duration varies with document size, rendering and provider latency.
    activity: "5 minutes",
    icon: "screener",
    audience: "pst",
    workflow: "stage_gate",
    availability: "available",
  },
  {
    id: "chunker",
    href: "/chunker",
    title: "Chunker",
    description:
      "Turn DOCX and PPTX files into ordered, citable text, table, and image blocks.",
    activity: "1 minute",
    icon: "chunker",
    audience: "shared",
    workflow: "utility",
    availability: "available",
  },
  {
    id: "searcher",
    href: "/searcher",
    title: "Searcher",
    description:
      "Search selected evidence sources directly and review raw findings without an analysis around them.",
    activity: "1 minute",
    icon: "searcher",
    audience: "shared",
    workflow: "utility",
    availability: "available",
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
