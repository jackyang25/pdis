/**
 * Which fields a Scout continuation searches, read from and written to the review draft.
 *
 * The draft's `not_searched_fields` is the only record of the choice. It holds the
 * exclusions rather than the selection, so a draft nobody touched searches every field, as
 * it always did. Every helper here derives from that list; none keeps a second copy.
 */

import type { ScoutResponse, Variable } from "./api.ts";
import { countLabel } from "./count-label.ts";

type Draft = Pick<ScoutResponse, "variables" | "not_searched_fields">;

/** The fields retrieval can investigate: a stated target with its exact spans. Mirrors `_searchable`. */
export function searchableFields(result: Pick<ScoutResponse, "variables">): Variable[] {
  return (result.variables ?? []).filter(
    (variable) => variable.document_target && variable.document_spans?.length,
  );
}

/** The exclusions after one field is searched or left out, in document order. */
export function withFieldSearched(result: Draft, name: string, searched: boolean): string[] {
  const excluded = new Set(result.not_searched_fields ?? []);
  if (searched) excluded.delete(name);
  else excluded.add(name);
  return searchableFields(result)
    .map((variable) => variable.name)
    .filter((field) => excluded.has(field));
}

/** The exclusions when every field is searched, or none is. */
export function withEveryFieldSearched(result: Draft, searched: boolean): string[] {
  return searched ? [] : searchableFields(result).map((variable) => variable.name);
}

export type FieldSelectionSummary = {
  searched: number;
  total: number;
  /** "12 of 26 fields will be searched." */
  sentence: string;
  /** Why the continuation cannot start, or "" when it can. */
  blocked: string;
};

export function fieldSelectionSummary(result: Draft): FieldSelectionSummary {
  const fields = searchableFields(result);
  const excluded = new Set(result.not_searched_fields ?? []);
  const total = fields.length;
  const searched = fields.filter((variable) => !excluded.has(variable.name)).length;
  return {
    searched,
    total,
    sentence: searched === total && total > 1
      ? `All ${countLabel(total, "field")} will be searched.`
      : `${searched} of ${countLabel(total, "field")} will be searched.`,
    blocked: total > 0 && searched === 0 ? "Select at least one field to search." : "",
  };
}
