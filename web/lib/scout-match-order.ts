import type { Match } from "./api.ts";

/**
 * How the matches under one variable are ordered for reading.
 *
 * Kept out of the page because it is pure logic over published fields, so it can be
 * tested without rendering, and because the page's other Scout helpers already live
 * beside it in `lib`.
 *
 * Display only. Nothing here filters, groups, or alters a match; the returned list
 * holds exactly the matches it was given.
 */

/**
 * Relation first, and this order is deliberate: a contradiction is the most
 * consequential thing a reader can see, and an unrelated finding the least.
 */
export const RELATION_ORDER: Record<Match["relation"], number> = {
  contradicts: 0,
  extends: 1,
  confirms: 2,
  unrelated: 3,
};

/**
 * The newest date any of a match's supporting findings reports, or null.
 *
 * A match rests on several findings, so it is as recent as its most recent source.
 * `published_at` is ISO-8601 with an offset from every lane that supplies one, so
 * these compare correctly as strings. Deliberately not parsed: a malformed value
 * would become 1970 and sort to the bottom without anyone noticing.
 */
export function newestSourceDate(match: Match): string | null {
  let newest: string | null = null;
  for (const finding of match.insight.supporting_findings ?? []) {
    const published = finding.published_at;
    if (!published) continue;
    if (newest === null || published > newest) newest = published;
  }
  return newest;
}

/**
 * Order matches by relation, then by recency within each relation.
 *
 * Relation stays primary. What this adds is the tiebreak *inside* a relation, which
 * was previously retrieval order - so a 1997 paper could sit above a 2026 one for no
 * reason a reader could explain. Nobody chose that order; it was whatever arrived
 * first.
 *
 * Undated matches keep their relative order and follow the dated ones **within their
 * own relation group**, rather than sinking to the bottom of the list. That
 * containment is deliberate: in a real run half the findings carry no date and they
 * cluster in the web and Semantic Scholar lanes, so sinking them would quietly demote
 * two whole sources under the guise of sorting.
 *
 * The comparator ends on the original index, which makes the order total: equal
 * matches never swap between renders, whatever the engine's sort does.
 */
export function sortMatchesForReading(matches: Match[]): Match[] {
  return [...matches]
    .map((match, index) => ({ match, index, date: newestSourceDate(match) }))
    .sort(
      (a, b) =>
        RELATION_ORDER[a.match.relation] - RELATION_ORDER[b.match.relation]
        // Dated before undated, inside the relation group.
        || Number(a.date === null) - Number(b.date === null)
        // Newest first.
        || (a.date && b.date ? b.date.localeCompare(a.date) : 0)
        // Original position last, so the order is total and stable.
        || a.index - b.index,
    )
    .map((entry) => sortSupportingFindings(entry.match));
}

/**
 * Order one match's sources the same way the matches themselves are ordered.
 *
 * A match is positioned by the newest date among these, and that date is shown
 * nowhere on the match itself. Leaving the sources in retrieval order therefore
 * hid the sort key behind a jumble of dates, and a correct order read as an
 * arbitrary one. Newest first puts the key on the first line, so the ordering
 * explains itself without labelling anything.
 *
 * The undated rule is inherited rather than re-decided: they follow the dated
 * sources and keep their relative order, because about half of all findings
 * carry no date and sinking them would demote the web and Semantic Scholar lanes
 * under the guise of sorting.
 */
export function sortSupportingFindings(match: Match): Match {
  const findings = match.insight.supporting_findings ?? [];
  if (findings.length < 2) return match;
  const sorted = findings
    .map((finding, index) => ({ finding, index }))
    .sort(
      (a, b) =>
        Number(!a.finding.published_at) - Number(!b.finding.published_at)
        || (a.finding.published_at && b.finding.published_at
          ? b.finding.published_at.localeCompare(a.finding.published_at)
          : 0)
        || a.index - b.index,
    )
    .map((entry) => entry.finding);
  return { ...match, insight: { ...match.insight, supporting_findings: sorted } };
}
