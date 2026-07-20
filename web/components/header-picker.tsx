"use client";

import { useEffect, useMemo, useState } from "react";
import { usePathname } from "next/navigation";
import { Label } from "./ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "./ui/select";
import {
  fetchDocumentTypes,
  fetchIndications,
  type DocumentType,
  type ToolName,
} from "@/lib/api";
import { useHeaderStore } from "@/lib/store";

const PATH_TO_TOOL: Record<string, ToolName> = {
  "/chunker": "chunker",
  "/inspector": "inspector",
  "/scout": "scout",
};

export function HeaderPicker() {
  const pathname = usePathname() ?? "";
  const tool = PATH_TO_TOOL[pathname] ?? null;
  const { header, setHeader } = useHeaderStore();
  const [docTypes, setDocTypes] = useState<DocumentType[] | null>(null);
  const [indications, setIndications] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchDocumentTypes()
      .then(setDocTypes)
      .catch((err: Error) => setError(err.message));
  }, []);

  useEffect(() => {
    if (!header.intervention_class) {
      setIndications([]);
      return;
    }
    fetchIndications(header.intervention_class)
      .then(setIndications)
      .catch(() => setIndications([]));
  }, [header.intervention_class]);

  const supported = useMemo(() => {
    if (!docTypes) return [];
    return tool ? docTypes.filter((d) => d.supports[tool]) : docTypes;
  }, [docTypes, tool]);

  const orgs = useMemo(
    () => Array.from(new Set(supported.map((d) => d.org))).sort(),
    [supported],
  );
  const sourceTypes = useMemo(
    () =>
      Array.from(
        new Set(supported.filter((d) => d.org === header.org).map((d) => d.source_type)),
      ).sort(),
    [supported, header.org],
  );
  const interventions = useMemo(
    () =>
      Array.from(
        new Set(
          supported
            .filter((d) => d.org === header.org && d.source_type === header.source_type)
            .map((d) => d.intervention_class),
        ),
      ).sort(),
    [supported, header.org, header.source_type],
  );

  if (error) {
    return (
      <div className="flex min-h-[264px] items-center sm:min-h-[124px] lg:min-h-[264px]">
        <p className="text-xs leading-5 text-destructive">Could not load configuration: {error}</p>
      </div>
    );
  }
  if (!docTypes) return <ConfigurationPlaceholder />;

  return (
    <div className="flex flex-col gap-4 sm:grid sm:grid-cols-2 lg:flex">
      <Field label="Organization">
        <Select
          value={header.org}
          onValueChange={(value) =>
            setHeader({
              org: value,
              source_type: undefined,
              intervention_class: undefined,
              indication: undefined,
            })
          }
          disabled={orgs.length === 0}
        >
          <SelectTrigger>
            <SelectValue placeholder="Select" />
          </SelectTrigger>
          <SelectContent>
            {orgs.map((o) => (
              <SelectItem key={o} value={o}>
                {displayLabel(o)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </Field>

      <Field label="Source type" disabled={!header.org}>
        <Select
          value={header.source_type}
          onValueChange={(value) =>
            setHeader({
              source_type: value,
              intervention_class: undefined,
              indication: undefined,
            })
          }
          disabled={!header.org || sourceTypes.length === 0}
        >
          <SelectTrigger>
            <SelectValue placeholder="Select" />
          </SelectTrigger>
          <SelectContent>
            {sourceTypes.map((st) => (
              <SelectItem key={st} value={st}>
                {displayLabel(st)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </Field>

      <Field label="Intervention" disabled={!header.source_type}>
        <Select
          value={header.intervention_class}
          onValueChange={(value) =>
            setHeader({ intervention_class: value, indication: undefined })
          }
          disabled={!header.source_type || interventions.length === 0}
        >
          <SelectTrigger>
            <SelectValue placeholder="Select" />
          </SelectTrigger>
          <SelectContent>
            {interventions.map((iv) => (
              <SelectItem key={iv} value={iv}>
                {displayLabel(iv)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </Field>

      <Field
        label="Indication"
        disabled={!header.intervention_class}
      >
        <Select
          value={header.indication}
          onValueChange={(value) => setHeader({ indication: value })}
          disabled={!header.intervention_class || indications.length === 0}
        >
          <SelectTrigger>
            <SelectValue placeholder="Select" />
          </SelectTrigger>
          <SelectContent>
            {indications.map((ta) => (
              <SelectItem key={ta} value={ta}>
                {displayLabel(ta)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </Field>
    </div>
  );
}

function ConfigurationPlaceholder() {
  return (
    <div
      className="flex flex-col gap-4 sm:grid sm:grid-cols-2 lg:flex"
      aria-busy="true"
      aria-label="Loading configuration"
    >
      {["Organization", "Source type", "Intervention", "Indication"].map((label) => (
        <Field key={label} label={label} disabled>
          <div className="h-9 rounded-md border border-input bg-muted/40" aria-hidden="true" />
        </Field>
      ))}
    </div>
  );
}

function Field({
  label,
  disabled,
  children,
}: {
  label: string;
  disabled?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className={disabled ? "min-w-0 opacity-50" : "min-w-0"}>
      <div className="mb-1.5">
        <Label>{label}</Label>
      </div>
      {children}
    </div>
  );
}

const ACRONYMS = new Set([
  "who",
  "bmgf",
  "tpp",
  "ipdp",
  "ppc",
  "hiv",
  "tb",
  "rsv",
  "hpv",
  "covid19",
]);

// Tokens with non-uniform casing (lowercase prefix + uppercase acronym).
const SPECIAL_LABELS: Record<string, string> = {
  itpp: "iTPP",
  ctpp: "cTPP",
};

function displayLabel(value: string): string {
  const lower = value.toLowerCase();
  if (SPECIAL_LABELS[lower]) return SPECIAL_LABELS[lower];
  if (ACRONYMS.has(lower)) return value.toUpperCase();
  return value
    .split("_")
    .map((w) => (w ? w[0].toUpperCase() + w.slice(1) : ""))
    .join(" ");
}
