"use client";

import { useEffect, useMemo, useState } from "react";
import { usePathname } from "next/navigation";
import {
  fetchContexts,
  fetchDocumentTypes,
  fetchInspectorConfiguration,
  type Header,
  type InspectorFactField,
  type ContextOption,
  type DocumentType,
  type ToolName,
} from "./api";

const PATH_TO_TOOL: Record<string, ToolName> = {
  "/chunker": "chunker",
  "/inspector": "inspector",
  "/scout": "scout",
  "/aligner": "aligner",
  "/screener": "screener",
};

// Separate authorities, cached independently. A rejected request must not poison
// later mounts; context discovery never depends on document-type discovery.
let contextsRequest: Promise<ContextOption[]> | null = null;
let documentTypesRequest: Promise<DocumentType[]> | null = null;

function loadContexts(): Promise<ContextOption[]> {
  contextsRequest ??= fetchContexts().catch((error: Error) => {
    contextsRequest = null;
    throw error;
  });
  return contextsRequest;
}

function loadDocumentTypes(): Promise<DocumentType[]> {
  documentTypesRequest ??= fetchDocumentTypes().catch((error: Error) => {
    documentTypesRequest = null;
    throw error;
  });
  return documentTypesRequest;
}

function useSupportedCatalog<T extends { supports: Partial<Record<ToolName, boolean>> }>(
  load: () => Promise<T[]>,
): { entries: T[] | null; error: string | null } {
  const pathname = usePathname() ?? "";
  const tool = PATH_TO_TOOL[pathname] ?? null;
  const [entries, setEntries] = useState<T[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    setError(null);
    load()
      .then((loaded) => live && setEntries(loaded))
      .catch((err: Error) => live && setError(err.message));
    return () => { live = false; };
  }, [load]);

  const supported = useMemo(() => {
    if (!entries) return null;
    return tool ? entries.filter((item) => item.supports[tool]) : entries;
  }, [entries, tool]);

  return { entries: supported, error };
}

export function useSupportedContexts() {
  const { entries: contexts, error } = useSupportedCatalog(loadContexts);
  return { contexts, error };
}

export function useSupportedDocumentTypes() {
  const { entries: types, error } = useSupportedCatalog(loadDocumentTypes);
  return { types, error };
}

/** The selected profile declares its extra facts; the browser owns no guideline rules. */
export function useInspectorConfiguration(header: Header) {
  const { org, source_type, intervention_class } = header;
  const key = JSON.stringify([org, source_type, intervention_class]);
  const [loaded, setLoaded] = useState<{ key: string; fields: InspectorFactField[]; error: string | null } | null>(null);
  useEffect(() => {
    if (!org || !source_type || !intervention_class) return;
    let live = true;
    fetchInspectorConfiguration({ org, source_type, intervention_class })
      .then(catalog => live && setLoaded({ key, fields: catalog.applicability_facts, error: null }))
      .catch((error: Error) => live && setLoaded({ key, fields: [], error: error.message }));
    return () => { live = false; };
  }, [org, source_type, intervention_class, key]);
  return loaded?.key === key ? { ...loaded, ready: !loaded.error } : { fields: [], error: null, ready: false };
}
