/**
 * Searcher's text fields, and what each is called wherever a reader sees one.
 *
 * Searcher owns what a search accepts: `SEARCH_TEXT_FIELDS` mirrors the list of that name in
 * `services/searcher/pipeline.py`, which the API's request and the Assistant's suggested
 * search are built from, and `search-fields.test.ts` fails if this copy diverges. The labels
 * are the form's own, so a suggestion names a field exactly as the page it opens does.
 */

export const SEARCH_TEXT_FIELDS = [
  "query",
  "condition",
  "intervention",
  "product",
  "population",
  "outcome",
  "region",
  "published_since",
] as const;

export type SearchTextField = (typeof SEARCH_TEXT_FIELDS)[number];
export type SearchTextFields = Partial<Record<SearchTextField, string>>;

export const SEARCH_FIELD_LABEL: Record<SearchTextField, string> = {
  query: "Search query",
  condition: "Condition",
  intervention: "Health product type",
  product: "Product",
  population: "Population",
  outcome: "Outcome",
  region: "Region",
  published_since: "Published since",
};
