import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { fetchContexts, fetchDocumentTypes } from "./api.ts";

test("a gate-only context is discoverable when no document type is configured", async (t) => {
  const context = { org: "bank-only", intervention_class: "small_molecule", supports: { screener: true } };
  t.mock.method(globalThis, "fetch", async (url: string) => {
    if (url.endsWith("/api/configs/contexts")) return Response.json({ contexts: [context] });
    assert.ok(url.endsWith("/api/configs/document-types"));
    return Response.json({ document_types: [] });
  });
  assert.deepEqual(await fetchContexts(), [context]);
  assert.deepEqual(await fetchDocumentTypes(), []);
});

test("shared context controls and source-type controls consume independent catalogs", () => {
  const source = readFileSync(new URL("../components/configuration-fields.tsx", import.meta.url), "utf8");
  const context = source.slice(source.indexOf("export function ContextFields()"), source.indexOf("export function SourceTypeField("));
  assert.match(context, /useSupportedContexts\(\)/);
  assert.doesNotMatch(context, /useSupportedDocumentTypes|loadDocumentTypes/);
  const catalog = readFileSync(new URL("./use-configuration-catalog.ts", import.meta.url), "utf8");
  const contexts = catalog.slice(catalog.indexOf("export function useSupportedContexts()"), catalog.indexOf("export function useSupportedDocumentTypes()"));
  assert.match(contexts, /useSupportedCatalog\(loadContexts\)/);
  const types = catalog.slice(catalog.indexOf("export function useSupportedDocumentTypes()"));
  assert.match(types, /useSupportedCatalog\(loadDocumentTypes\)/);
});
