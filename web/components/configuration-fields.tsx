"use client";

import { useEffect, useMemo, useState } from "react";
import { usePathname } from "next/navigation";
import { ErrorMessage } from "@/components/ui/error-message";
import {
  ConfigField,
  ConfigFieldGrid,
  ConfigSelect,
  ConfigurationShell,
} from "./ui/config-field";
import {
  fetchDocumentTypes,
  fetchIndications,
  type DocumentType,
  type ToolName,
} from "@/lib/api";
import { useHeaderStore } from "@/lib/store";
import { displayLabel } from "@/lib/display-label";

/**
 * The shared parts of a tool's configuration rail.
 *
 * Three buckets sit side by side in every tool's panel, and which bucket a field
 * belongs to is decided by one question: does the value leave the tool?
 *
 *   1. Context      org, intervention, indication - always one each, every tool
 *   2. Document type  source type - one per document, so one or several
 *   3. Run knobs    a tool's own parameters, e.g. a date bound
 *
 * Buckets 1 and 2 are contract data: they select the configuration, are stamped
 * on every parsed block, travel in saved result files, and are read across tools
 * by Ask. They must mean the same thing everywhere, which is why this module owns
 * them and exposes no way to rename, reorder, or omit a field.
 *
 * Bucket 3 never leaves its tool, so no shared component owns it. A tool composes
 * the primitives in `ui/config-field.tsx` directly and puts its own fields in the
 * same rail.
 *
 * Context and document type are split because their cardinality differs, not
 * their status: Aligner needs a source type per document while everything else
 * needs one. They used to be one fixed block of four fields, which is why Aligner
 * could not use it and rebuilt the other three by hand.
 */

const PATH_TO_TOOL: Record<string, ToolName> = {
  "/chunker": "chunker",
  "/inspector": "inspector",
  "/scout": "scout",
  "/aligner": "aligner",
  "/expert": "expert",
};

/**
 * Document types this tool supports, fetched once per session.
 *
 * The promise is cached at module scope because two fields on one page both need
 * the list, and the catalogue cannot change while the page is open. Without it,
 * a rail with a context picker and three source-type selects would issue four
 * identical requests.
 */
let documentTypesRequest: Promise<DocumentType[]> | null = null;

function loadDocumentTypes(): Promise<DocumentType[]> {
  documentTypesRequest ??= fetchDocumentTypes().catch((error: Error) => {
    // Clear the cache so a transient failure can be retried by a later mount
    // rather than being remembered for the rest of the session.
    documentTypesRequest = null;
    throw error;
  });
  return documentTypesRequest;
}

export function useSupportedDocumentTypes(): {
  types: DocumentType[] | null;
  error: string | null;
} {
  const pathname = usePathname() ?? "";
  const tool = PATH_TO_TOOL[pathname] ?? null;
  const [types, setTypes] = useState<DocumentType[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    loadDocumentTypes()
      .then((loaded) => live && setTypes(loaded))
      .catch((err: Error) => live && setError(err.message));
    return () => {
      live = false;
    };
  }, []);

  const supported = useMemo(() => {
    if (!types) return null;
    return tool ? types.filter((item) => item.supports[tool]) : types;
  }, [types, tool]);

  return { types: supported, error };
}

/**
 * Bucket 1: the context every tool needs exactly one of.
 *
 * Bound to the shared store rather than to props, which is what makes a choice
 * follow the user between tools. Deliberately takes no configuration - a caller
 * that could pass a field list could let two tools disagree, which is the drift
 * this component exists to prevent.
 */
export function ContextFields() {
  const { header, setHeader } = useHeaderStore();
  const { types, error } = useSupportedDocumentTypes();
  const [indications, setIndications] = useState<string[]>([]);

  useEffect(() => {
    if (!header.intervention_class) {
      setIndications([]);
      return;
    }
    let live = true;
    fetchIndications(header.intervention_class)
      .then((loaded) => live && setIndications(loaded))
      .catch(() => live && setIndications([]));
    return () => {
      live = false;
    };
  }, [header.intervention_class]);

  const orgs = useMemo(
    () => unique((types ?? []).map((item) => item.org)),
    [types],
  );
  const interventions = useMemo(
    () =>
      unique(
        (types ?? [])
          .filter((item) => item.org === header.org)
          .map((item) => item.intervention_class),
      ),
    [types, header.org],
  );

  if (error) {
    return (
      <div className="flex min-h-[264px] items-center sm:min-h-[124px] lg:min-h-[264px]">
        <ErrorMessage size="xs">Could not load configuration: {error}</ErrorMessage>
      </div>
    );
  }
  if (!types) return <FieldPlaceholder labels={CONTEXT_LABELS} />;

  return (
    <ConfigFieldGrid>
      <ConfigField label="Organization">
        <ConfigSelect
          value={header.org}
          options={toOptions(orgs)}
          // Every later choice is filtered by this one, so all of them clear.
          onChange={(value) =>
            setHeader({
              org: value,
              intervention_class: undefined,
              indication: undefined,
              source_type: undefined,
            })
          }
        />
      </ConfigField>

      {/*
        "Intervention class", not "Intervention": the options are classes - drug, vaccine,
        monoclonal antibody - and the value travels as `intervention_class`. Searcher
        carries the same concept under the same name beside a separate Product field, and
        one concept labelled two ways is how a reader learns to distrust both.
      */}
      <ConfigField label="Intervention class" disabled={!header.org}>
        <ConfigSelect
          value={header.intervention_class}
          options={toOptions(interventions)}
          disabled={!header.org}
          onChange={(value) =>
            setHeader({
              intervention_class: value,
              indication: undefined,
              source_type: undefined,
            })
          }
        />
      </ConfigField>

      <ConfigField label="Indication" disabled={!header.intervention_class}>
        <ConfigSelect
          value={header.indication}
          options={toOptions(indications)}
          disabled={!header.intervention_class}
          onChange={(value) => setHeader({ indication: value })}
        />
      </ConfigField>
    </ConfigFieldGrid>
  );
}

/**
 * Bucket 2: one document's type.
 *
 * Props-driven rather than store-bound, because how many of these a tool needs is
 * the tool's own business: one for a single-document tool, one per row for
 * Aligner. What the field means is not - hence one component rather than a
 * dropdown each page builds itself.
 */
export function SourceTypeField({
  value,
  onChange,
  label = "Document type",
  exclude = [],
  hint = true,
  action,
}: {
  value: string | undefined;
  onChange: (value: string) => void;
  label?: string;
  /** Types other selects have taken, so a tool cannot pick one twice. */
  exclude?: readonly string[];
  /**
   * Show the consequence note. On by default; a tool rendering several of these
   * shows it on the first row only, because the sentence is about the field rather
   * than about one document.
   */
  hint?: boolean;
  /**
   * A control belonging to this field, on the select's own line — a tool holding
   * several documents uses it for the row's remove button.
   */
  action?: React.ReactNode;
}) {
  const header = useHeaderStore((state) => state.header);
  const { types } = useSupportedDocumentTypes();

  const options = useMemo(
    () =>
      unique(
        (types ?? [])
          .filter(
            (item) =>
              item.org === header.org
              && item.intervention_class === header.intervention_class,
          )
          .map((item) => item.source_type),
      ).filter((option) => option === value || !exclude.includes(option)),
    [types, header.org, header.intervention_class, value, exclude],
  );

  const ready = Boolean(header.org && header.intervention_class);
  return (
    <ConfigField
      label={label}
      disabled={!ready}
      action={action}
      note={hint ? <SourceTypeHint /> : undefined}
    >
      <ConfigSelect
        value={value}
        options={toOptions(options)}
        disabled={!ready}
        onChange={onChange}
      />
    </ConfigField>
  );
}

/**
 * The one consequence of this field that nothing else states.
 *
 * Deliberately says "what it is read against" rather than "which rubric": the type
 * selects Inspector's rubric and Scout's attribute configuration, but Aligner holds
 * one source-type-neutral configuration and Expert's bank is keyed by gate. Naming
 * the rubric would be precise for two tools and false for two.
 *
 * It lives here rather than in each tool's copy because the sentence is about the
 * field, and four tools writing their own version of it is the drift this module
 * exists to prevent. Nothing validates that the chosen type matches the document, so
 * this warning is the only thing standing between a mis-selection and a confident
 * answer about the wrong thing.
 */
function SourceTypeHint() {
  return (
    <p className="mt-1.5 text-[11px] leading-relaxed text-muted-foreground">
      Sets how the document is parsed and what it is read against. Nothing checks
      that the file matches, so the wrong type gives a confident result about the
      wrong thing.
    </p>
  );
}

/**
 * The rail for a tool that reads one document: context, then that document's type.
 *
 * Aligner composes `ContextFields` and `SourceTypeField` itself because it needs
 * several of the latter.
 */
export function ConfigurationFields() {
  const setHeader = useHeaderStore((state) => state.setHeader);
  const sourceType = useHeaderStore((state) => state.header.source_type);
  return (
    <ConfigurationShell>
      <ContextFields />
      <div className="mt-4">
        <SourceTypeField
          value={sourceType}
          onChange={(value) => setHeader({ source_type: value })}
        />
      </div>
    </ConfigurationShell>
  );
}

const CONTEXT_LABELS = ["Organization", "Intervention class", "Indication"] as const;

function FieldPlaceholder({ labels }: { labels: readonly string[] }) {
  return (
    <ConfigFieldGrid aria-busy="true" aria-label="Loading configuration">
      {labels.map((label) => (
        <ConfigField key={label} label={label} disabled>
          <div className="h-9 rounded-md border border-input bg-muted/40" aria-hidden="true" />
        </ConfigField>
      ))}
    </ConfigFieldGrid>
  );
}

function toOptions(values: readonly string[]) {
  return values.map((value) => ({ value, label: displayLabel(value) }));
}

function unique(values: string[]): string[] {
  return Array.from(new Set(values)).sort();
}
