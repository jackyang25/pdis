/**
 * What a search box on a result toolbar does, in one place.
 *
 * Every tool has rows worth finding and only two had a way to find them, so Aligner and
 * Screener led their bands with a label instead - the same word the tab above already
 * said, because there was nothing else to put there.
 *
 * The rule the tools now share: **a query filters the leaf rows, and a container with
 * nothing left in it disappears.** Scout already worked that way because its leaves are
 * its top level. Inspector did not: it kept a section whose units matched and then showed
 * every unit in it, so searching "efficacy" returned a section of twenty rows with no
 * indication which one was the hit.
 *
 * Case- and whitespace-insensitive, and nothing else. No fuzzy matching, no stemming, no
 * ranking - this codebase refuses fuzzy string comparison wherever a decision rests on
 * it, and while a search is only a filter, the moment it guesses it starts hiding rows a
 * reader can see should be there.
 */
export function normalizeQuery(query: string): string {
  return query.trim().toLowerCase();
}

/**
 * Whether any of these texts contains the query.
 *
 * An empty query matches everything, which is what makes "no filter" and "filter that
 * matches all" the same code path rather than a branch at every call site.
 */
export function matchesQuery(query: string, ...texts: (string | null | undefined)[]): boolean {
  if (!query) return true;
  return texts.some((text) => (text ?? "").toLowerCase().includes(query));
}
