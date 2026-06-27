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
  "/reviewer": "reviewer",
  "/scout": "scout",
};

type FieldRole = "selects config" | "labels output" | "scopes search";

const ROLES: Record<ToolName, Record<keyof Roles, FieldRole>> = {
  chunker: {
    org: "selects config",
    source_type: "selects config",
    intervention: "selects config",
    indication: "labels output",
  },
  reviewer: {
    org: "selects config",
    source_type: "selects config",
    intervention: "selects config",
    indication: "labels output",
  },
  scout: {
    org: "selects config",
    source_type: "selects config",
    intervention: "selects config",
    indication: "scopes search",
  },
};

type Roles = {
  org: FieldRole;
  source_type: FieldRole;
  intervention: FieldRole;
  indication: FieldRole;
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

  if (error) return <p className="text-xs text-destructive">{error}</p>;
  if (!docTypes) return <p className="text-xs text-muted-foreground">Loading...</p>;

  const roles: Roles =
    tool && tool in ROLES
      ? ROLES[tool]
      : {
          org: "labels output",
          source_type: "labels output",
          intervention: "labels output",
          indication: "labels output",
        };

  return (
    <div className="flex flex-col gap-4">
      <Field label="Org" role={roles.org}>
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

      <Field label="Source type" role={roles.source_type} disabled={!header.org}>
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

      <Field label="Intervention" role={roles.intervention} disabled={!header.source_type}>
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
        role={roles.indication}
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

function Field({
  label,
  role,
  disabled,
  children,
}: {
  label: string;
  role: FieldRole;
  disabled?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className={disabled ? "opacity-60" : undefined}>
      <div className="mb-1.5 flex items-baseline justify-between gap-2">
        <Label>{label}</Label>
        <span className="text-[10px] uppercase tracking-wide text-muted-foreground">{role}</span>
      </div>
      {children}
    </div>
  );
}

const ACRONYMS = new Set([
  "who",
  "bmgf",
  "tpp",
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
