/**
 * Where each product identity icon lives, keyed by the name code refers to it by.
 *
 * Data, so it sits in `lib/` rather than beside the component that draws it. Two
 * reasons: `lib/product-knowledge.ts` needs the name type and `lib/` must not
 * depend on `components/`, and a test has to be able to check that every name a
 * catalogue uses resolves to a real file — which it cannot do through a `.tsx`.
 *
 * Keep this limited to tools and named agents. Navigation, actions, status, file
 * types, and other interface grammar use Lucide, so the two visual systems never
 * compete at the same semantic layer.
 */
export const PDIS_ICON_PATHS = {
  // Native workspace tools
  inspector: "freehand/form-edition-clipboard-check--Streamline-Freehand.svg",
  aligner: "freehand/business-workflow-compare--Streamline-Freehand.svg",
  scout: "freehand/hierarchy-web--Streamline-Freehand.svg",
  screener: "freehand/human-resources-rating-man--Streamline-Freehand.svg",
  chunker: "freehand/data-transfer-document-module--Streamline-Freehand.svg",
  searcher: "freehand/search-magnifier--Streamline-Freehand.svg",
  archivist: "freehand/archive-drawer-1--Streamline-Freehand.svg",

  // External workflow identities
  evaluator: "freehand/business-cash-scale-balance--Streamline-Freehand.svg",
  roadmap: "freehand/business-workflow-project-management--Streamline-Freehand.svg",
  "executive-summary": "freehand/office-file-text--Streamline-Freehand.svg",
  "stage-gate": "freehand/task-list-clipboard-clock--Streamline-Freehand.svg",

  // Named workspace agent
  chat: "freehand/help-headphones-customer-support-human--Streamline-Freehand.svg",
} as const;

export type PdisIconName = keyof typeof PDIS_ICON_PATHS;

/**
 * The product icon for one published workflow graph.
 *
 * Here rather than in the graph component, because a component that renders during
 * static export is the wrong place for a lookup that can miss: adding Screener's graph
 * to `shared/product_knowledge.json` without an entry compiled cleanly and then
 * failed the whole `/docs` prerender with "Cannot read properties of undefined
 * (reading 'split')". A missing entry now shows the wrong picture, and
 * `product-knowledge.test.ts` fails so it does not stay wrong.
 */
const GRAPH_ICONS: Record<string, PdisIconName> = {
  inspector: "inspector",
  aligner: "aligner",
  screener: "screener",
  scout: "scout",
  chunker: "chunker",
  searcher: "searcher",
  archivist: "archivist",
  chat: "chat",
};

export function graphIcon(id: string): PdisIconName {
  return GRAPH_ICONS[id] ?? "chunker";
}

export function graphIconIsDeclared(id: string): boolean {
  return id in GRAPH_ICONS;
}
