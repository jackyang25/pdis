"use client";

import { useCallback, useEffect, useState } from "react";
import { Archive, Loader2 } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { EmptyState } from "@/components/empty-state";
import { ErrorMessage } from "@/components/ui/error-message";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { SectionHeading } from "@/components/ui/section-heading";
import { CitedMark, Quoted } from "@/components/ui/evidence-text";
import { markCitedText } from "@/lib/cited-text";
import { displayLabel } from "@/lib/display-label";
import { cn } from "@/lib/utils";
import {
  fetchArchivistCorpus,
  queryArchivist,
  type ArchivistAnswer,
  type ArchivistColumn,
  type ArchivistCorpus,
  type ArchivistRecord,
  type ArchivistSourceTypeGroup,
} from "@/lib/api";
import {
  answeredOf,
  attributeLabel,
  attributeTotals,
  collapseValues,
  documentTitle,
  fenceSummary,
  filterableColumns,
} from "@/lib/archivist-view";

/**
 * Archivist reads the archive. It runs nothing, so this page has no upload, no progress
 * and no run history: the corpus was built and reviewed in advance, and a query is a
 * filter over it.
 *
 * The one thing the layout must never do is merge document types. An iTPP states a
 * class-level ambition and a cTPP states one candidate's commitment, so they are separate
 * headings under every attribute even when only one of them has values - the shape of the
 * answer says so, and the page follows it rather than flattening it for tidiness.
 */
export default function ArchivistPage() {
  const [corpus, setCorpus] = useState<ArchivistCorpus | null>(null);
  const [answer, setAnswer] = useState<ArchivistAnswer | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // What the reader asked for, empty meaning "whatever the route defaults to". The class
  // actually in force is read off the response rather than mirrored into state: mirroring
  // it made this effect set the value it depends on, so every load fetched twice.
  const [requestedClass, setRequestedClass] = useState("");
  const [indications, setIndications] = useState<Set<string>>(new Set());
  const [sourceTypes, setSourceTypes] = useState<Set<string>>(new Set());
  const [attributes, setAttributes] = useState<Set<string>>(new Set());
  const [tags, setTags] = useState<Record<string, Set<string>>>({});

  const interventionClass = corpus?.intervention_class ?? "";

  useEffect(() => {
    let active = true;
    fetchArchivistCorpus(requestedClass || undefined)
      .then((held) => {
        if (!active) return;
        setCorpus(held);
        // Filters are cleared on a class change rather than carried over: the columns and
        // their vocabularies are declared per class, so a tag selected under one class
        // may not exist under the next.
        setIndications(new Set());
        setSourceTypes(new Set());
        setAttributes(new Set());
        setTags({});
        setAnswer(null);
      })
      .catch((cause) => {
        if (active) setError((cause as Error).message);
      });
    return () => {
      active = false;
    };
  }, [requestedClass]);

  const read = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      setAnswer(
        await queryArchivist({
          intervention_class: interventionClass,
          attributes: [...attributes],
          indications: [...indications],
          source_types: [...sourceTypes],
          tags: Object.entries(tags)
            .filter(([, values]) => values.size > 0)
            .map(([attribute, values]) => ({ attribute, values: [...values] })),
        }),
      );
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      setBusy(false);
    }
  }, [interventionClass, attributes, indications, sourceTypes, tags]);

  const empty = corpus != null && corpus.documents.length === 0;

  return (
    <div className="mx-auto max-w-5xl px-6 py-10">
      <PageHeader
        title="Archivist"
        description="What the Foundation's own product profiles have said before, with the quote and the document behind every value."
      />

      {error && <ErrorMessage>{error}</ErrorMessage>}

      {empty && (
        // `absence`, not `clear`: nothing has been checked here. An unbuilt corpus is a
        // precondition, and a tick would claim a search that never happened.
        <EmptyState
          message="Nothing has been indexed yet"
          detail={
            "The corpus is built from a folder of documents and a reviewed manifest, then " +
            "committed. Until that has been run there is nothing to read, which is a " +
            "different state from an archive that holds no answer to your question."
          }
        />
      )}

      {corpus && !empty && (
        <div className="flex flex-col gap-6">
          <section className="rounded-lg border border-border bg-card p-5">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <Label asChild>
                <h2>Read the archive</h2>
              </Label>
              <p className="text-xs text-muted-foreground">
                {corpus.documents.length} profiles
                {corpus.built_at &&
                  ` · indexed ${corpus.built_at.slice(0, 10)}`}
              </p>
            </div>

            <div className="mt-5 flex flex-col gap-5">
              {corpus.intervention_classes.length > 1 && (
                <ChipRow
                  title="Intervention class"
                  help="Which columns exist at all is declared per class."
                  options={corpus.intervention_classes}
                  selected={new Set([interventionClass])}
                  onToggle={setRequestedClass}
                />
              )}

              <ChipRow
                title="Attribute"
                help="Leave empty to read every column."
                options={corpus.columns.map((column) => column.attribute)}
                labelFor={attributeLabel}
                selected={attributes}
                onToggle={(value) => setAttributes(toggled(attributes, value))}
              />

              {corpus.indications.length > 1 && (
                <ChipRow
                  title="Indication"
                  help="Only the indications the archive holds."
                  options={corpus.indications}
                  selected={indications}
                  onToggle={(value) =>
                    setIndications(toggled(indications, value))
                  }
                />
              )}

              {corpus.source_types.length > 1 && (
                <ChipRow
                  title="Document type"
                  help="Narrows which profiles are read. Answers are never merged across types."
                  options={corpus.source_types}
                  selected={sourceTypes}
                  onToggle={(value) =>
                    setSourceTypes(toggled(sourceTypes, value))
                  }
                />
              )}

              {filterableColumns(corpus.columns).map((column) => (
                <ChipRow
                  key={column.attribute}
                  title={attributeLabel(column.attribute)}
                  help={`Keeps the profiles written for these. ${fenceSummary(column)}`}
                  options={column.tags}
                  selected={tags[column.attribute] ?? new Set()}
                  onToggle={(value) =>
                    setTags({
                      ...tags,
                      [column.attribute]: toggled(
                        tags[column.attribute] ?? new Set(),
                        value,
                      ),
                    })
                  }
                />
              ))}

              <div>
                <Button onClick={read} disabled={busy}>
                  {busy ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <Archive className="mr-2 h-4 w-4" />
                  )}
                  Read the archive
                </Button>
              </div>
            </div>
          </section>

          {answer && <Answer answer={answer} columns={corpus.columns} />}
        </div>
      )}
    </div>
  );
}

function toggled(current: Set<string>, value: string): Set<string> {
  const next = new Set(current);
  if (next.has(value)) next.delete(value);
  else next.add(value);
  return next;
}

/** One row of selectable chips. Multi-select, because every filter here is a set. */
function ChipRow({
  title,
  help,
  options,
  selected,
  onToggle,
  labelFor = displayLabel,
}: {
  title: string;
  help: string;
  options: readonly string[];
  selected: Set<string>;
  onToggle: (value: string) => void;
  labelFor?: (value: string) => string;
}) {
  return (
    <div>
      <p className="text-xs font-semibold tracking-tight">{title}</p>
      <p className="mt-0.5 text-xs leading-5 text-muted-foreground">{help}</p>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {options.map((option) => (
          <button
            key={option}
            type="button"
            onClick={() => onToggle(option)}
            aria-pressed={selected.has(option)}
            className={cn(
              "rounded-full border px-2.5 py-1 text-[11px] font-medium leading-4 transition-colors motion-reduce:transition-none",
              selected.has(option)
                ? "border-transparent bg-secondary text-secondary-foreground"
                : "border-border bg-card text-muted-foreground hover:text-foreground",
            )}
          >
            {labelFor(option)}
          </button>
        ))}
      </div>
    </div>
  );
}

function Answer({
  answer,
  columns,
}: {
  answer: ArchivistAnswer;
  columns: ArchivistColumn[];
}) {
  if (answer.documents.length === 0) {
    return (
      <section className="rounded-lg border border-border bg-card p-5">
        <h2 className="text-sm font-semibold">
          No profile matches those filters
        </h2>
        <p className="mt-2 text-xs leading-5 text-muted-foreground">
          The archive holds profiles, but none with that combination. This is a
          fact about the filters, not about what the profiles said.
        </p>
      </section>
    );
  }
  return (
    <div className="flex flex-col gap-4">
      <p className="text-xs text-muted-foreground">
        Reading {answer.documents.length}{" "}
        {answer.documents.length === 1 ? "profile" : "profiles"}.
      </p>
      {answer.attributes.map((group) => {
        const { answered, total } = attributeTotals(group);
        const column = columns.find(
          (item) => item.attribute === group.attribute,
        );
        return (
          <section
            key={group.attribute}
            className="rounded-lg border border-border bg-card p-5"
          >
            <SectionHeading
              title={attributeLabel(group.attribute)}
              description={column ? fenceSummary(column) : ""}
              // The denominator, always. "Three specified this" reads as a finding; three
              // of nineteen reads as the finding it actually is.
              trailing={`${answered} of ${total} specified it`}
            />
            <div className="mt-4 flex flex-col gap-4">
              {group.groups.map((sourceGroup) => (
                <SourceType
                  key={sourceGroup.source_type}
                  group={sourceGroup}
                  answer={answer}
                />
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}

/**
 * One document type's answers. Never merged with another type's.
 *
 * The heading is drawn even when this type has only silence to report, because "no cTPP
 * in the archive specified this" is one of the two answers a reader came for.
 */
function SourceType({
  group,
  answer,
}: {
  group: ArchivistSourceTypeGroup;
  answer: ArchivistAnswer;
}) {
  const { answered, total } = answeredOf(group);
  return (
    <div className="border-t border-border pt-4 first:border-t-0 first:pt-0">
      <div className="flex flex-wrap items-baseline gap-2">
        <Badge variant="outline">{displayLabel(group.source_type)}</Badge>
        <span className="text-xs text-muted-foreground">
          {answered} of {total}
        </span>
      </div>

      {collapseValues(group.values).map((value) => (
        <div key={`${value.bound} ${value.stated}`} className="mt-3">
          <div className="flex flex-wrap items-baseline gap-2">
            <p className="text-sm font-medium">{value.stated}</p>
            {value.bound !== "single" && (
              <Badge variant="muted">{displayLabel(value.bound)}</Badge>
            )}
            {value.records.length > 1 && (
              <span className="text-xs text-muted-foreground">
                {value.records.length} profiles
              </span>
            )}
          </div>
          {value.records.map((record) => (
            <Provenance
              key={`${record.document_id} ${record.block_id}`}
              record={record}
              answer={answer}
            />
          ))}
        </div>
      ))}

      {group.uncertain.length > 0 && (
        <div className="mt-3">
          <p className="text-xs font-semibold text-muted-foreground">
            Flagged for review
          </p>
          {group.uncertain.map((record) => (
            <div
              key={`${record.document_id} ${record.block_id}`}
              className="mt-2"
            >
              <p className="text-sm">
                {record.stated || "No value could be read"}
                {record.reason && (
                  <span className="text-muted-foreground">
                    {" "}
                    · {record.reason}
                  </span>
                )}
              </p>
              {record.quote && <Provenance record={record} answer={answer} />}
            </div>
          ))}
        </div>
      )}

      {group.silent.length > 0 && (
        <p className="mt-3 text-xs leading-5 text-muted-foreground">
          Did not specify it:{" "}
          {group.silent
            .map((id) => documentTitle(answer.documents, id))
            .join(", ")}
        </p>
      )}
    </div>
  );
}

/**
 * The quote, the block it sits in, and where in the document that block was.
 *
 * All three, because the quote alone misleads: "24 months" reads differently when the
 * same block says "for the lyophilized presentation only". The quote is marked inside
 * its block rather than repeated above it, so a reader sees the value in its context in
 * one pass instead of comparing two strings.
 */
function Provenance({
  record,
  answer,
}: {
  record: ArchivistRecord;
  answer: ArchivistAnswer;
}) {
  // The shared locator, not a local `indexOf`. Archivist's own invariant guarantees the
  // quote sits inside the block, so a naive match happens to work here - but it was a second
  // implementation of the same idea, and Scout's showed that a quote can differ from its
  // block by whitespace alone. One tested version, so the two tools cannot drift.
  const passage = markCitedText(record.block_text, [record.quote]);
  const found = passage.unplaced.length === 0 && record.quote.length > 0;
  return (
    <div className="mt-1.5">
      <Quoted size="prominent" className="mt-0">
        {found ? (
          <>
            {passage.segments.map((segment, index) =>
              segment.cited ? (
                <CitedMark key={index}>{segment.text}</CitedMark>
              ) : (
                <span key={index}>{segment.text}</span>
              ),
            )}
          </>
        ) : (
          record.block_text
        )}
      </Quoted>
      <p className="mt-1 text-[11px] leading-4 text-muted-foreground">
        {documentTitle(answer.documents, record.document_id)}
        {record.section_label && ` · ${displayLabel(record.section_label)}`}
        {` · ${record.block_id}`}
        {record.condition_stated && ` · applies to ${record.condition_stated}`}
      </p>
    </div>
  );
}
