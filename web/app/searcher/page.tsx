"use client";

import { FormEvent, useEffect, useState } from "react";
import { ExternalLink, Loader2, Search, X } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { ErrorMessage } from "@/components/ui/error-message";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { ConfigDateInput, ConfigSelect } from "@/components/ui/config-field";
import { cn } from "@/lib/utils";
import {
  fetchSearchSources,
  runSearcher,
  type SearchLane,
  type SearchSource,
} from "@/lib/api";
import { RunHistory } from "@/components/run-history";
import { runLabel } from "@/lib/result-file";
import { useSearcherSession } from "@/lib/session";
import { SourceAttributions } from "@/components/source-attributions";
import type { Finding } from "@/lib/api";
import { EYEBROW } from "@/lib/typography";

export default function SearcherPage() {
  const [query, setQuery] = useState("");
  const [condition, setCondition] = useState("");
  const [intervention, setIntervention] = useState("");
  const [product, setProduct] = useState("");
  const [population, setPopulation] = useState("");
  const [outcome, setOutcome] = useState("");
  const [region, setRegion] = useState("");
  const [publishedSince, setPublishedSince] = useState("");
  const [entities, setEntities] = useState<StatedEntity[]>([]);
  const [entityName, setEntityName] = useState("");
  const [entityType, setEntityType] = useState("");
  const [sources, setSources] = useState<SearchSource[]>([]);
  const [sourcesLoaded, setSourcesLoaded] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const {
    result,
    busy,
    error,
    addResult,
    setResult,
    setBusy,
    setStage,
    setError,
  } = useSearcherSession();

  useEffect(() => {
    let active = true;
    fetchSearchSources()
      .then((available) => {
        if (!active) return;
        setSources(available);
        setSelected(
          new Set(
            available
              .filter((source) => source.default_enabled)
              .map((source) => source.key),
          ),
        );
      })
      .catch((cause) => {
        if (active) setError((cause as Error).message);
      })
      .finally(() => {
        if (active) setSourcesLoaded(true);
      });
    return () => {
      active = false;
    };
  }, [setError]);

  function toggle(id: string) {
    const source = sources.find((candidate) => candidate.key === id);
    if (!source?.configured || !reachable(source, entities)) return;
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const canRun = query.trim().length > 0 && selected.size > 0 && !busy;
  const unreachableLabels = sources
    .filter((source) => source.configured && !reachable(source, entities))
    .map((source) => source.label);
  // Only the types a registered source can actually address. Derived from the same
  // `/sources` payload the toggles read, so the page holds no list of its own.
  // Named from the lanes' own declaration, so the note cannot claim a narrowing a
  // provider never applies.
  const regionLabels = sources
    .filter((source) => selected.has(source.key) && source.reads.includes("region"))
    .map((source) => source.label);
  const dateBoundLabels = sources
    .filter((source) => selected.has(source.key) && source.honors_date_bound)
    .map((source) => source.label);
  const addressableTypes = Array.from(
    new Set(sources.flatMap((source) => source.required_entity_types)),
  ).sort();

  // A source selected while it was reachable must not stay selected once the entity that
  // made it reachable is removed: the run would send a request the planner then rules
  // out, and the reader would read the skip as a fault rather than as their own edit.
  useEffect(() => {
    setSelected((previous) => {
      const next = new Set(
        Array.from(previous).filter((key) => {
          const source = sources.find((candidate) => candidate.key === key);
          return !source || reachable(source, entities);
        }),
      );
      return next.size === previous.size ? previous : next;
    });
  }, [entities, sources]);

  function addEntity() {
    const name = entityName.trim();
    if (!name || !entityType) return;
    setEntities((previous) =>
      previous.some(
        (entity) => entity.name === name && entity.type === entityType,
      )
        ? previous
        : [...previous, { name, type: entityType }],
    );
    setEntityName("");
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!canRun) return;
    setBusy(true);
    setError(null);
    setStage("search");
    setResult(null);
    try {
      const res = await runSearcher(
        query.trim(),
        Array.from(selected),
        {
          condition: condition.trim(),
          intervention: intervention.trim(),
          entities: entities
            .map((entity) => `${entity.name}:${entity.type}`)
            .join(","),
          product: product.trim(),
          population: population.trim(),
          outcome: outcome.trim(),
          region: region.trim(),
          publishedSince,
        },
        setStage,
      );
      addResult(res);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
      setStage(null);
    }
  }

  return (
    <>
      <PageHeader
        title="Searcher"
        description="Search registered evidence sources through one normalized workspace."
      />
      <div className="flex flex-col gap-6">
        <form
          onSubmit={onSubmit}
          className="rounded-lg border border-border bg-card p-5"
        >
          <div className="flex flex-col gap-2 sm:flex-row">
            <div className="relative flex-1">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="e.g. recent FDA guidance on RSV vaccines"
                className="h-9 w-full rounded-md border border-input bg-background pl-9 pr-3 text-sm outline-none placeholder:text-muted-foreground focus:ring-2 focus:ring-ring/20 disabled:cursor-not-allowed disabled:opacity-50"
                disabled={busy}
              />
            </div>
            <Button className="min-w-[6.5rem]" type="submit" disabled={!canRun}>
              {busy ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Searching
                </>
              ) : (
                "Search"
              )}
            </Button>
          </div>
          {/*
            The two facets the field-addressed sources anchor on. Styled like the query
            input above rather than through the rail primitives, because this card is not
            a configuration rail and `ConfigFieldGrid` exists to solve the rail's 17rem
            problem, which does not apply here. The notes are not decoration: left blank,
            an adapter anchors on the query text itself, and a reader who does not know
            that reads six empty lanes as an absence of evidence.
          */}
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <div className="min-w-0">
              <div className="mb-1.5">
                <Label>Condition</Label>
              </div>
              <input
                type="text"
                value={condition}
                onChange={(e) => setCondition(e.target.value)}
                placeholder="e.g. resected melanoma"
                className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm outline-none placeholder:text-muted-foreground focus:ring-2 focus:ring-ring/20 disabled:cursor-not-allowed disabled:opacity-50"
                disabled={busy}
              />
              <p className="mt-1.5 text-xs text-muted-foreground">
                Anchors every registry and database request. Left blank, they
                anchor on the query text instead, which rarely matches a
                condition field.
              </p>
            </div>
            <div className="min-w-0">
              <div className="mb-1.5">
                <Label>Intervention class</Label>
              </div>
              <input
                type="text"
                value={intervention}
                onChange={(e) => setIntervention(e.target.value)}
                placeholder="e.g. vaccine"
                className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm outline-none placeholder:text-muted-foreground focus:ring-2 focus:ring-ring/20 disabled:cursor-not-allowed disabled:opacity-50"
                disabled={busy}
              />
              <p className="mt-1.5 text-xs text-muted-foreground">
                The kind of intervention, which is what Scout carries here.
                Scopes the request. Ignored by sources with no intervention
                field.
              </p>
            </div>
            <div className="min-w-0">
              <div className="mb-1.5">
                <Label>Product</Label>
              </div>
              <input
                type="text"
                value={product}
                onChange={(e) => setProduct(e.target.value)}
                placeholder="e.g. intismeran autogene"
                className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm outline-none placeholder:text-muted-foreground focus:ring-2 focus:ring-ring/20 disabled:cursor-not-allowed disabled:opacity-50"
                disabled={busy}
              />
              <p className="mt-1.5 text-xs text-muted-foreground">
                One named product. Added as a second, narrower request beside
                the class rather than replacing it, so a name a registry files
                differently still returns the broader result.
              </p>
            </div>
            <div className="min-w-0">
              <div className="mb-1.5">
                <Label>Population</Label>
              </div>
              <input
                type="text"
                value={population}
                onChange={(e) => setPopulation(e.target.value)}
                placeholder="e.g. resected stage III"
                className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm outline-none placeholder:text-muted-foreground focus:ring-2 focus:ring-ring/20 disabled:cursor-not-allowed disabled:opacity-50"
                disabled={busy}
              />
              <p className="mt-1.5 text-xs text-muted-foreground">
                Who the question is about. Becomes the phrase PubMed and
                Semantic Scholar search for, in place of the whole query.
              </p>
            </div>
            <div className="min-w-0">
              <div className="mb-1.5">
                <Label>Outcome</Label>
              </div>
              <input
                type="text"
                value={outcome}
                onChange={(e) => setOutcome(e.target.value)}
                placeholder="e.g. overall survival"
                className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm outline-none placeholder:text-muted-foreground focus:ring-2 focus:ring-ring/20 disabled:cursor-not-allowed disabled:opacity-50"
                disabled={busy}
              />
              <p className="mt-1.5 text-xs text-muted-foreground">
                What is measured. Takes precedence over Population as that
                phrase, since it names the question more precisely.
              </p>
            </div>
            <div className="min-w-0">
              <div className="mb-1.5">
                <Label>Region</Label>
              </div>
              <input
                type="text"
                value={region}
                onChange={(e) => setRegion(e.target.value)}
                placeholder="e.g. Kenya"
                className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm outline-none placeholder:text-muted-foreground focus:ring-2 focus:ring-ring/20 disabled:cursor-not-allowed disabled:opacity-50"
                disabled={busy}
              />
              <p className="mt-1.5 text-xs text-muted-foreground">
                {regionLabels.length > 0
                  ? `Restricts ${regionLabels.join(", ")} to trials running there. Other sources ignore it.`
                  : "No selected source can filter by location, so this changes nothing."}
              </p>
            </div>
            <div className="min-w-0">
              <div className="mb-1.5">
                <Label>Published since</Label>
              </div>
              <ConfigDateInput
                value={publishedSince}
                onChange={setPublishedSince}
                max={new Date().toISOString().slice(0, 10)}
                disabled={busy}
              />
              <p className="mt-1.5 text-xs text-muted-foreground">
                {dateBoundLabels.length > 0
                  ? `Asked of ${dateBoundLabels.join(", ")} directly, so the window changes what they rank. Other sources ignore it.`
                  : "No selected source can filter by date, so this changes nothing."}
              </p>
            </div>
          </div>
          <div className="mt-4 flex min-h-8 flex-wrap items-center gap-2">
            <span className="mr-1 text-xs text-muted-foreground">Sources</span>
            {!sourcesLoaded && (
              <>
                <span className="h-8 w-20 rounded-md border border-border bg-muted" />
                <span className="h-8 w-24 rounded-md border border-border bg-muted" />
                <span className="h-8 w-16 rounded-md border border-border bg-muted" />
              </>
            )}
            {sources.map((source) => {
              const on = selected.has(source.key);
              const unreachable = !reachable(source, entities);
              return (
                <button
                  key={source.key}
                  type="button"
                  onClick={() => toggle(source.key)}
                  disabled={busy || !source.configured || unreachable}
                  title={
                    !source.configured
                      ? "Backend connector not configured"
                      : unreachable
                        ? `Name a ${source.required_entity_types.join(" or ")} below to reach this source.`
                        : undefined
                  }
                  aria-pressed={on}
                  className={cn(
                    "h-8 rounded-md border px-3 text-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/20 disabled:opacity-50 motion-reduce:transition-none",
                    on
                      ? "border-foreground bg-foreground text-background"
                      : "border-border bg-background text-muted-foreground hover:text-foreground",
                  )}
                >
                  {source.label}
                </button>
              );
            })}
            {sourcesLoaded && selected.size === 0 && (
              <span className="text-xs text-destructive">
                Select at least one source.
              </span>
            )}
          </div>
          {/*
            The fourth slot of the request. Here rather than beside Condition because it
            reads as a consequence of the source row above it: these are the sources that
            were dim a moment ago, and this is what un-dims them.
          */}
          <div className="mt-4">
            <div className="mb-1.5">
              <Label>Named subject</Label>
            </div>
            <div className="flex flex-col gap-2 sm:flex-row">
              <input
                type="text"
                value={entityName}
                onChange={(e) => setEntityName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key !== "Enter") return;
                  // Enter adds the subject rather than submitting the form, which would
                  // run a search that does not yet include what was just typed.
                  e.preventDefault();
                  addEntity();
                }}
                placeholder="e.g. BRAF"
                className="h-9 flex-1 rounded-md border border-input bg-background px-3 text-sm outline-none placeholder:text-muted-foreground focus:ring-2 focus:ring-ring/20 disabled:cursor-not-allowed disabled:opacity-50"
                disabled={busy}
              />
              <div className="sm:w-44">
                <ConfigSelect
                  value={entityType || undefined}
                  options={addressableTypes.map((type) => ({
                    value: type,
                    label: type.replace(/^\w/, (c) => c.toUpperCase()),
                  }))}
                  disabled={busy}
                  onChange={setEntityType}
                />
              </div>
              <Button
                type="button"
                variant="secondary"
                disabled={busy || !entityName.trim() || !entityType}
                onClick={addEntity}
              >
                Add
              </Button>
            </div>
            {entities.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {entities.map((entity) => (
                  <button
                    key={`${entity.name}:${entity.type}`}
                    type="button"
                    disabled={busy}
                    onClick={() =>
                      setEntities((previous) =>
                        previous.filter(
                          (held) =>
                            held.name !== entity.name ||
                            held.type !== entity.type,
                        ),
                      )
                    }
                    className="group/entity flex h-7 items-center gap-1.5 rounded-md border border-border bg-background px-2 text-xs text-foreground disabled:opacity-50"
                  >
                    <span>
                      {entity.name}
                      <span className="text-muted-foreground">
                        {" "}
                        · {entity.type}
                      </span>
                    </span>
                    <X className="h-3 w-3 text-muted-foreground group-hover/entity:text-foreground" />
                  </button>
                ))}
              </div>
            )}
            <p className="mt-1.5 text-xs text-muted-foreground">
              {unreachableLabels.length > 0
                ? `${unreachableLabels.join(", ")} address their API by a named subject rather than a phrase. Name one to reach them.`
                : "Every source can now build a request from what you have stated."}
            </p>
          </div>
        </form>

        {error && <ErrorMessage>{error}</ErrorMessage>}

        {result && <Findings result={result} sources={sources} />}
      </div>
    </>
  );
}

function Findings({
  result,
  sources,
}: {
  result: { query: string; findings: Finding[]; lanes?: SearchLane[] };
  sources: SearchSource[];
}) {
  const { results, selectedId, selectResult, removeResult } =
    useSearcherSession();
  const labels = new Map(sources.map((source) => [source.key, source.label]));

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2 pb-1 text-sm text-muted-foreground">
        <p>
          {result.findings.length} finding
          {result.findings.length === 1 ? "" : "s"} for &quot;{result.query}
          &quot;
        </p>
        <span className="flex items-center gap-2">
          <RunHistory
            runs={results}
            selectedId={selectedId}
            onSelect={selectResult}
            onRemove={removeResult}
            label={(value) => runLabel(value, "searcher")}
          />
        </span>
      </div>
      <Lanes lanes={result.lanes ?? []} sources={sources} />
      {result.findings.map((finding) => (
        <article
          key={finding.url}
          className="rounded-lg border border-border bg-card p-4"
        >
          <div className="flex items-start gap-3">
            <Badge variant="muted">
              {labels.get(finding.source) ?? humanizeSource(finding.source)}
            </Badge>
            <a
              href={finding.url}
              target="_blank"
              rel="noreferrer"
              className="flex-1 text-sm font-medium leading-snug text-foreground hover:underline"
            >
              {finding.title}
            </a>
            <ExternalLink className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          </div>
          <p className="mt-2 truncate font-mono text-[10px] text-muted-foreground/70">
            {finding.url}
          </p>
          {finding.excerpt ? (
            <p className="mt-3 whitespace-pre-wrap text-sm leading-relaxed">
              {finding.excerpt}
            </p>
          ) : (
            <p className="mt-3 text-xs italic text-muted-foreground">
              No cited excerpt - model did not quote this source.
            </p>
          )}
        </article>
      ))}
      <SourceAttributions findings={result.findings} />
    </div>
  );
}

/**
 * What every selected source did, including the ones that produced nothing.
 *
 * The counted breakdown this replaced was derived from the findings, so a source that
 * returned nothing, was skipped, or failed outright did not appear at all — all three
 * rendered as absence, and absence read as "no evidence exists". These rows come from
 * the run's outcomes instead, which keep the three distinct.
 *
 * The query shown is the native one the provider received. For a field-addressed source
 * that is not the text typed into the box, and the difference is usually the explanation
 * for a zero.
 *
 * Counts are per request, before cross-lane deduplication, so they can add up to more
 * than the number of findings shown. Labelled "returned" for that reason: the header
 * above owns the number of findings, and these rows own what each source sent back.
 */
function Lanes({
  lanes,
  sources,
}: {
  lanes: SearchLane[];
  sources: SearchSource[];
}) {
  if (lanes.length === 0) return null;
  const labels = new Map(sources.map((source) => [source.key, source.label]));
  const classOf = new Map(sources.map((source) => [source.key, source.evidence_class]));
  // Grouped by what each lane is responsible for, in the order the lanes ran. A flat
  // list answers "did this source return anything"; the grouping answers the question a
  // reader actually has, which is whether a kind of evidence came back at all - one
  // registry returning nothing reads very differently from every registry returning
  // nothing. Read from each lane's own declaration, so a new lane groups itself.
  const groups: { name: string; lanes: SearchLane[] }[] = [];
  for (const lane of lanes) {
    const name = classOf.get(lane.source) ?? "general";
    const group = groups.find((candidate) => candidate.name === name);
    if (group) group.lanes.push(lane);
    else groups.push({ name, lanes: [lane] });
  }
  return (
    <div className="rounded-lg border border-border bg-card">
      <p className="border-b border-border px-4 py-2 text-xs text-muted-foreground">
        Sources searched
      </p>
      {groups.map((group) => (
        <div key={group.name}>
          <p className={cn("border-b border-border bg-foreground/[0.045] px-4 py-1.5", EYEBROW)}>
            {group.name}
          </p>
          <ul className="divide-y divide-border">
            {group.lanes.map((lane, at) => (
              <li
                key={`${lane.source}-${at}`}
                className="flex flex-wrap items-baseline gap-x-3 gap-y-1 px-4 py-2.5 text-xs"
              >
                <span className="min-w-[8rem] font-medium text-foreground">
                  {labels.get(lane.source) ?? humanizeSource(lane.source)}
                </span>
                <code className="min-w-0 flex-1 break-all font-mono text-[10px] text-muted-foreground">
                  {/* A ruled-out lane built no request, so there is no query to show. */}
                  {lane.query ||
                    (lane.status === "skipped" ? "no request sent" : "")}
                </code>
                {lane.status === "complete" ? (
                  <span
                    className={cn(
                      "shrink-0 tabular-nums",
                      lane.returned === 0
                        ? "text-muted-foreground"
                        : "text-foreground",
                    )}
                  >
                    {lane.returned} returned
                  </span>
                ) : (
                  <span
                    className={cn(
                      "shrink-0",
                      lane.status === "failed"
                        ? "text-destructive"
                        : "text-muted-foreground",
                    )}
                  >
                    {lane.status}
                    {lane.detail ? `: ${lane.detail}` : ""}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

/** One named subject the request states, and what kind of thing it is. */
type StatedEntity = { name: string; type: string };

/**
 * Whether the request as composed can reach this source.
 *
 * A source declaring `required_entity_types` addresses its API by a named subject, so it
 * plans nothing until the request names one: Open Targets asks
 * `target_disease:<gene>|<disease>` and has no query without the gene.
 *
 * A property of the request, not of the source. The first version of this read only the
 * declaration and disabled those sources permanently, which said the wrong thing - it
 * looked like a fact about the source when it was a missing field on this page. Now the
 * toggle follows what the reader has stated, so naming a gene lights up the sources that
 * can use one.
 *
 * Read from the source's own declaration rather than a list kept here, so a new
 * subject-addressed source needs no change on this page.
 */
function reachable(source: SearchSource, entities: StatedEntity[]): boolean {
  if (source.required_entity_types.length === 0) return true;
  return entities.some((entity) =>
    source.required_entity_types.includes(entity.type),
  );
}

function humanizeSource(source: string): string {
  return source
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}
