"use client";

import { useEffect, useMemo, useState } from "react";
import { usePathname } from "next/navigation";
import { ErrorMessage } from "@/components/ui/error-message";
import { ConfigField, ConfigFieldGrid, ConfigSelect } from "./ui/config-field";
import {
  fetchDocumentTypes,
  fetchIndications,
  type DocumentType,
  type ToolName,
} from "@/lib/api";
import { useHeaderStore } from "@/lib/store";
import { displayLabel } from "@/lib/display-label";

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
        <ErrorMessage size="xs">Could not load configuration: {error}</ErrorMessage>
      </div>
    );
  }
  if (!docTypes) return <ConfigurationPlaceholder />;

  return (
    <ConfigFieldGrid>
      <ConfigField label="Organization">
        <ConfigSelect
          value={header.org}
          options={orgs.map((value) => ({ value, label: displayLabel(value) }))}
          onChange={(value) =>
            setHeader({
              org: value,
              source_type: undefined,
              intervention_class: undefined,
              indication: undefined,
            })
          }
        />
      </ConfigField>

      <ConfigField label="Source type" disabled={!header.org}>
        <ConfigSelect
          value={header.source_type}
          options={sourceTypes.map((value) => ({ value, label: displayLabel(value) }))}
          disabled={!header.org}
          onChange={(value) =>
            setHeader({
              source_type: value,
              intervention_class: undefined,
              indication: undefined,
            })
          }
        />
      </ConfigField>

      <ConfigField label="Intervention" disabled={!header.source_type}>
        <ConfigSelect
          value={header.intervention_class}
          options={interventions.map((value) => ({ value, label: displayLabel(value) }))}
          disabled={!header.source_type}
          onChange={(value) => setHeader({ intervention_class: value, indication: undefined })}
        />
      </ConfigField>

      <ConfigField label="Indication" disabled={!header.intervention_class}>
        <ConfigSelect
          value={header.indication}
          options={indications.map((value) => ({ value, label: displayLabel(value) }))}
          disabled={!header.intervention_class}
          onChange={(value) => setHeader({ indication: value })}
        />
      </ConfigField>
    </ConfigFieldGrid>
  );
}

function ConfigurationPlaceholder() {
  return (
    <ConfigFieldGrid aria-busy="true" aria-label="Loading configuration">
      {["Organization", "Source type", "Intervention", "Indication"].map((label) => (
        <ConfigField key={label} label={label} disabled>
          <div className="h-9 rounded-md border border-input bg-muted/40" aria-hidden="true" />
        </ConfigField>
      ))}
    </ConfigFieldGrid>
  );
}
