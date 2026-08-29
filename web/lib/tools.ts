export type ToolIcon =
  | "inspector"
  | "aligner"
  | "scout"
  | "screener"
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
  /**
   * What this tool judges, against what, and what it is not.
   *
   * One grammar for all four, because a reader choosing between them is comparing:
   * `<what is judged> against <the authority>: <what you learn>. <Territory>, not
   * <the neighbour's territory>.`
   *
   * One grammar for every tool that reads documents:
   *
   *     <what is read>  against | across  <the authority>:  <what you learn>
   *
   * `against` for the four that judge, `across` for Archivist, which does not. The
   * preposition is where the difference sits: you hold a document *against* a standard
   * and you look *across* a corpus, and a reader meets that distinction before reading
   * a word of the boundary clause on the page.
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
   *
   * No exception for Archivist, though it is the one tool that would need a different
   * clause: it judges nothing, so it owns no territory to name, and what it needs headed
   * off instead is a reader taking "past iTPPs required twelve months" as advice to
   * require twelve months. Its limit arrives with its page, like everyone else's. One
   * card carrying a sentence the other five do not is the inconsistency it was meant to
   * fix.
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
    // No `href` while this is coming soon. The card would not link either way - the card
    // checks `comingSoon || !href` - but this is the only link to `/archivist` anywhere in
    // the app, so leaving it would be a route offered by nothing and reachable by one
    // stale value. The page under `app/archivist` is untouched and still answers if the
    // URL is typed; what is being withdrawn is the way in.
    title: "Archivist",
    // Imperative, like Chunker and Searcher, and for the reason the family rule gives:
    // this performs a lookup rather than judging a document. It names no authority
    // because it has none - the corpus is its authority, and a corpus is data.
    description:
      "One attribute across every past iTPP and cTPP: what each one required, how many never mentioned it, and the line every value was read from.",
    // No `activity`. It read "approx. 1 min", the floor of the shared scale, chosen so a
    // corpus query would not sit beside "approx. 20 min" as a second scale. An estimate is
    // a promise about a run, and there is nothing here to run yet.
    icon: "archivist",
    // Owned by the PST team, who write these profiles, rather than shared: no other
    // tool reads the corpus, which is what makes Chunker and Searcher shared.
    audience: "pst",
    // The utility family by this file's own rule - it performs a task rather than
    // rendering a verdict - which is a different axis from who owns it.
    workflow: "utility",
    delivery: "workspace",
    availability: "coming_soon",
  },
  {
    id: "inspector",
    href: "/inspector",
    title: "Inspector",
    description:
      "One document against its rubric: whether it states what the template asks for, usably.",
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
      "One document’s targets against external evidence: whether its numbers hold up against comparable measurements and development precedent.",
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
      "The iTPP, cTPP, and IPDP against each other: whether each honours the one before it, requirement by requirement.",
    // Same arithmetic as Screener's, one step longer: each comparison reads its
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
    id: "screener",
    href: "/screener",
    title: "Screener",
    description:
      "The iTPP, cTPP, and IPDP against a stage gate’s question bank: what is still unanswered, and which discipline it goes to.",
    // Observed, not estimated. 80 questions at six concurrent is ~14 waves, and each
    // call returns one decision and one sentence — a few hundred bytes — against a
    // document context the provider caches after the first. The count of calls is not
    // what costs time here; the size of each answer is, and these are tiny.
    activity: "approx. 1 min",
    icon: "screener",
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
      "Turn evaluation findings and screener feedback into an organized roadmap of recommendations and actions.",
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
