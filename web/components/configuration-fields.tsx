"use client";

import { useEffect, useMemo, useState } from "react";
import { ErrorMessage } from "@/components/ui/error-message";
import {
  ConfigField,
  ConfigHelp,
  ConfigSelect,
  ConfigSectionHeading,
  ConfigurationShell,
} from "./ui/config-field";
import {
  fetchIndications,
} from "@/lib/api";
import { useSupportedContexts, useSupportedDocumentTypes } from "@/lib/use-configuration-catalog";
import { useHeaderStore } from "@/lib/store";
import { displayLabel } from "@/lib/display-label";

/**
 * Shared domain selectors. These own field meaning, available values and dependent
 * selection resets. They do not own grouping: ConfigurationShell lays out all
 * fields together, including the tool's own controls.
 */

/**
 * The context a document workflow needs exactly one of.
 *
 * Bound to the shared store rather than to props, which is what makes a choice
 * follow the user between tools. Deliberately takes no configuration - a caller
 * that could pass a field list could let two tools disagree, which is the drift
 * this component exists to prevent.
 */
export function ContextFields() {
  const { header, setHeader } = useHeaderStore();
  const { contexts, error } = useSupportedContexts();
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
    () => unique((contexts ?? []).map((item) => item.org)),
    [contexts],
  );
  const interventions = useMemo(
    () =>
      unique(
        (contexts ?? [])
          .filter((item) => item.org === header.org)
          .map((item) => item.intervention_class),
      ),
    [contexts, header.org],
  );

  if (error) {
    return (
      <div className="sm:col-span-2">
        <ErrorMessage size="xs">Could not load configuration: {error}</ErrorMessage>
      </div>
    );
  }
  if (!contexts) return <><ConfigSectionHeading>Context</ConfigSectionHeading><FieldPlaceholder labels={CONTEXT_LABELS} /></>;

  return (
    <>
      <ConfigSectionHeading>Context</ConfigSectionHeading>
      <ConfigField
        label="Organization"
        help="Organization and intervention class determine which configurations are available."
      >
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
      <ConfigField
        label="Intervention class"
        disabled={!header.org}
      >
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

      <ConfigField
        label="Indication"
        disabled={!header.intervention_class}
        help="The disease or condition. It travels with documents and results but does not select a rubric or question bank. Scout also checks it against the document and uses it in evidence searches."
      >
        <ConfigSelect
          value={header.indication}
          searchLabel="Search indications"
          options={toOptions(indications)}
          disabled={!header.intervention_class}
          onChange={(value) => setHeader({ indication: value })}
        />
      </ConfigField>
    </>
  );
}

/**
 * One document's type.
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
  const { types, error } = useSupportedDocumentTypes();

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
      help={hint ? "Sets how the document is parsed and what it is read against. Choosing the wrong type can produce a misleading result." : undefined}
      note={error ? <ErrorMessage size="xs">{error}</ErrorMessage> : hint ? <SourceTypeHint /> : undefined}
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
 * one source-type-neutral configuration. Naming the rubric would be precise for
 * two tools and false for Aligner. Screener does not request a source type.
 *
 * It lives here rather than in each tool's copy because the sentence is about the
 * field, and four tools writing their own version of it is the drift this module
 * exists to prevent. Nothing validates that the chosen type matches the document, so
 * this warning is the only thing standing between a mis-selection and a confident
 * answer about the wrong thing.
 */
function SourceTypeHint() {
  return (
    <ConfigHelp>
      Match the uploaded document. Its type is not checked automatically.
    </ConfigHelp>
  );
}

/**
 * The rail for a tool that reads one document: context, then that document's type.
 *
 * Aligner composes `ContextFields` and `SourceTypeField` itself because it needs
 * several of the latter.
 */
export function ConfigurationFields({ children }: { children?: React.ReactNode }) {
  const setHeader = useHeaderStore((state) => state.setHeader);
  const sourceType = useHeaderStore((state) => state.header.source_type);
  return (
    <ConfigurationShell>
      <ContextFields />
      <ConfigSectionHeading>Document selection</ConfigSectionHeading>
      <SourceTypeField
        value={sourceType}
        onChange={(value) => setHeader({ source_type: value })}
      />
      {children}
    </ConfigurationShell>
  );
}

const CONTEXT_LABELS = ["Organization", "Intervention class", "Indication"] as const;

function FieldPlaceholder({ labels }: { labels: readonly string[] }) {
  return (
    <>
      {labels.map((label) => (
        <ConfigField key={label} label={label} disabled>
          <div className="h-9 rounded-md border border-input bg-muted" role="status" aria-label={`Loading ${label.toLowerCase()}`} />
        </ConfigField>
      ))}
    </>
  );
}

function toOptions(values: readonly string[]) {
  return values.map((value) => ({ value, label: displayLabel(value) }));
}

function unique(values: string[]): string[] {
  return Array.from(new Set(values)).sort();
}
