/**
 * A Searcher run the Assistant proposed, and the address that opens it filled in.
 *
 * The Assistant never searches. When the workspace cannot answer, it sends an offer on its
 * own stream event: structured data naming the tool, the text fields, and any sources and
 * entities, which the chat renders as a control and Searcher reads back from its address.
 *
 * Searcher owns what a search accepts: the text fields are `search-fields.ts`, and source
 * keys and entity types arrive in the offer from Searcher's registry and are checked again
 * by the page.
 */

import { SEARCH_TEXT_FIELDS, type SearchTextFields } from "./search-fields.ts";

export type OfferedSource = { key: string; label: string };
export type OfferedEntity = { name: string; entity_type: string };
export type SearchOffer = {
  tool: "searcher";
  fields: SearchTextFields & { query: string };
  sources: OfferedSource[];
  entities: OfferedEntity[];
};
/** What Searcher's address carries: the same three parts, without the display labels. */
export type SearchHandoff = { fields: SearchTextFields; sources: string[]; entities: OfferedEntity[] };

/** The offer an event carried, or null when it is not one this interface can open. */
export function readSearchOffer(value: unknown): SearchOffer | null {
  if (typeof value !== "object" || value === null) return null;
  const { tool, fields, sources, entities } = value as Record<string, unknown>;
  if (tool !== "searcher" || typeof fields !== "object" || fields === null) return null;
  const kept: SearchTextFields = {};
  for (const name of SEARCH_TEXT_FIELDS) {
    const raw = (fields as Record<string, unknown>)[name];
    if (typeof raw === "string" && raw.trim()) kept[name] = raw.trim();
  }
  if (!kept.query) return null;
  return {
    tool,
    fields: { ...kept, query: kept.query },
    sources: listOf(sources).filter(
      (item): item is OfferedSource => typeof item?.key === "string" && typeof item?.label === "string",
    ),
    entities: listOf(entities).filter(
      (item): item is OfferedEntity => typeof item?.name === "string" && typeof item?.entity_type === "string",
    ),
  };
}

function listOf(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.filter((item) => typeof item === "object" && item !== null) : [];
}

/**
 * Searcher's page, with the offer in its address.
 *
 * Entities use the `name:type` form Searcher's form already submits, split at the last
 * colon on the way back because a type never contains one.
 */
export function searcherHref(offer: SearchOffer): string {
  const params = new URLSearchParams();
  for (const name of SEARCH_TEXT_FIELDS) {
    const value = offer.fields[name];
    if (value) params.set(name, value);
  }
  if (offer.sources.length) params.set("sources", offer.sources.map((source) => source.key).join(","));
  for (const entity of offer.entities) params.append("entity", `${entity.name}:${entity.entity_type}`);
  return `/searcher?${params.toString()}`;
}

/** What an address carries, for Searcher to start from. Unknown names are ignored. */
export function readSearchHandoff(search: string): SearchHandoff {
  const params = new URLSearchParams(search);
  const fields: SearchTextFields = {};
  for (const name of SEARCH_TEXT_FIELDS) {
    const value = params.get(name)?.trim();
    if (value) fields[name] = value;
  }
  const sources = (params.get("sources") ?? "").split(",").map((key) => key.trim()).filter(Boolean);
  const entities = params.getAll("entity").flatMap((raw) => {
    const split = raw.lastIndexOf(":");
    const name = raw.slice(0, split).trim();
    const entity_type = raw.slice(split + 1).trim();
    return split > 0 && name && entity_type ? [{ name, entity_type }] : [];
  });
  return { fields, sources, entities };
}
