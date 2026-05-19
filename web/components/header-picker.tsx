"use client";

import { useEffect, useState } from "react";
import { Label } from "./ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "./ui/select";
import { fetchTherapeuticAreas, fetchTriples, type TriplesResponse } from "@/lib/api";
import { useHeaderStore } from "@/lib/store";

const NONE_VALUE = "__none__";

export function HeaderPicker() {
  const { header, setHeader } = useHeaderStore();
  const [triples, setTriples] = useState<TriplesResponse | null>(null);
  const [therapeuticAreas, setTherapeuticAreas] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchTriples()
      .then((data) => {
        setTriples(data);
        setError(null);
      })
      .catch((err: Error) => setError(err.message));
  }, []);

  useEffect(() => {
    if (!header.intervention_class) {
      setTherapeuticAreas([]);
      return;
    }
    fetchTherapeuticAreas(header.intervention_class)
      .then(setTherapeuticAreas)
      .catch(() => setTherapeuticAreas([]));
  }, [header.intervention_class]);

  if (error) {
    return <p className="text-xs text-destructive">{error}</p>;
  }
  if (!triples) {
    return <p className="text-xs text-muted-foreground">Loading...</p>;
  }

  const sourceTypes = header.org ? triples.source_types_by_org[header.org] ?? [] : [];
  const interventions =
    header.org && header.source_type
      ? triples.interventions_by_org_source[`${header.org}__${header.source_type}`] ?? []
      : [];

  return (
    <div className="flex flex-col gap-4">
      <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        Document
      </div>

      <Field label="Org">
        <Select
          value={header.org}
          onValueChange={(value) =>
            setHeader({
              org: value,
              source_type: undefined,
              intervention_class: undefined,
              therapeutic_area: null,
            })
          }
        >
          <SelectTrigger>
            <SelectValue placeholder="Select" />
          </SelectTrigger>
          <SelectContent>
            {triples.orgs.map((org) => (
              <SelectItem key={org} value={org}>
                {org}
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
              therapeutic_area: null,
            })
          }
          disabled={!header.org}
        >
          <SelectTrigger>
            <SelectValue placeholder="Select" />
          </SelectTrigger>
          <SelectContent>
            {sourceTypes.map((st) => (
              <SelectItem key={st} value={st}>
                {st}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </Field>

      <Field label="Intervention" disabled={!header.source_type}>
        <Select
          value={header.intervention_class}
          onValueChange={(value) =>
            setHeader({ intervention_class: value, therapeutic_area: null })
          }
          disabled={!header.source_type}
        >
          <SelectTrigger>
            <SelectValue placeholder="Select" />
          </SelectTrigger>
          <SelectContent>
            {interventions.map((iv) => (
              <SelectItem key={iv} value={iv}>
                {iv}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </Field>

      <Field label="Therapeutic area" disabled={therapeuticAreas.length === 0}>
        <Select
          value={header.therapeutic_area ?? NONE_VALUE}
          onValueChange={(value) =>
            setHeader({ therapeutic_area: value === NONE_VALUE ? null : value })
          }
          disabled={therapeuticAreas.length === 0}
        >
          <SelectTrigger>
            <SelectValue placeholder="Optional" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={NONE_VALUE}>Any</SelectItem>
            {therapeuticAreas.map((ta) => (
              <SelectItem key={ta} value={ta}>
                {ta}
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
  children,
  disabled,
}: {
  label: string;
  children: React.ReactNode;
  disabled?: boolean;
}) {
  return (
    <div className={disabled ? "opacity-60" : ""}>
      <Label className="mb-1.5 block">{label}</Label>
      {children}
    </div>
  );
}
