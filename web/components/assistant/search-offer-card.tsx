import Link from "next/link";
import { ArrowRight } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PdisIcon } from "@/components/ui/pdis-icon";
import { SEARCH_FIELD_LABEL, SEARCH_TEXT_FIELDS, type SearchTextField } from "@/lib/search-fields";
import { searcherHref, type SearchOffer } from "@/lib/search-offer";

/**
 * A search the Assistant set up and the reader may run.
 *
 * It shows exactly what would be searched before anything is, and its one action opens
 * Searcher with those fields filled in: the reader reviews them and presses Run there. The
 * card itself runs nothing, which is what keeps Ask read-only.
 *
 * Built from the suite's parts - the tool's own mark, category badges for the fields, the
 * outline button - so it reads as PDIS inside an answer rather than as a widget dropped in.
 */
export function SearchOfferCard({ offer }: { offer: SearchOffer }) {
  const facets = SEARCH_TEXT_FIELDS.filter(
    (name): name is Exclude<SearchTextField, "query"> => name !== "query" && Boolean(offer.fields[name]),
  );
  // One row of what the search is scoped by: the stated fields, the named subjects, then the
  // sources it would ask, in the order Searcher's form lists them.
  const pills = [
    ...facets.map((name) => ({ key: name, label: SEARCH_FIELD_LABEL[name], value: offer.fields[name] })),
    ...offer.entities.map((entity) => ({ key: `entity:${entity.name}`, label: capitalised(entity.entity_type), value: entity.name })),
    ...(offer.sources.length
      ? [{ key: "sources", label: offer.sources.length === 1 ? "Source" : "Sources", value: offer.sources.map((source) => source.label).join(", ") }]
      : []),
  ];
  return (
    <section
      aria-label="Suggested search"
      className="mt-3 rounded-lg border border-border/70 bg-card p-3"
    >
      <p className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
        <PdisIcon name="searcher" className="h-3.5 w-3.5 shrink-0" />
        Suggested search
      </p>
      <p className="mt-1.5 text-sm text-foreground">{offer.fields.query}</p>
      {pills.length > 0 && (
        <ul className="mt-2 flex flex-wrap gap-1.5">
          {pills.map((pill) => (
            <li key={pill.key}>
              <Badge variant="outline" className="gap-1">
                <span className="text-muted-foreground">{pill.label}</span>
                {pill.value}
              </Badge>
            </li>
          ))}
        </ul>
      )}
      <div className="mt-3 flex justify-end">
        <Button asChild size="sm" variant="outline" className="gap-1.5">
          <Link href={searcherHref(offer)}>
            Open in Searcher
            <ArrowRight aria-hidden="true" className="h-3.5 w-3.5" />
          </Link>
        </Button>
      </div>
    </section>
  );
}

function capitalised(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1).replaceAll("_", " ");
}
