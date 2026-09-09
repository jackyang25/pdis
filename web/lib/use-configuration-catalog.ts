"use client";

import { useEffect, useMemo, useState } from "react";
import { usePathname } from "next/navigation";
import {
  fetchContexts,
  fetchDocumentTypes,
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
