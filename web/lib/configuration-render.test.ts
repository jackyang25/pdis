import assert from "node:assert/strict";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { loadComponent as loadRealComponent } from "../test-support/load-component.ts";

const root = fileURLToPath(new URL("..", import.meta.url));

// Node's strip-types runner cannot load TSX or Next aliases. Compile local
// components in memory, retaining real field rendering and replacing only state
// and network-backed hooks with a controlled catalog failure.
function loadComponent(path: string): any {
  return loadRealComponent(path, {
    "@/lib/use-configuration-catalog": {
      useSupportedDocumentTypes: () => ({ types: null, error: "Catalog unavailable" }),
    },
    "@/lib/store": {
      useHeaderStore: (select: (state: unknown) => unknown) => select({
        header: { org: "gates", intervention_class: "small_molecule" },
      }),
    },
    "@/lib/api": {},
  });
}

test("document catalog failure is visible beside its disabled selector", () => {
  const { SourceTypeField } = loadComponent(resolve(root, "components/configuration-fields.tsx"));
  const html = renderToStaticMarkup(React.createElement(SourceTypeField, {
    value: undefined, onChange: () => {},
  }));
  assert.match(html, /role="alert"/);
  assert.match(html, /Catalog unavailable/);
  assert.match(html, /disabled=""/);
});

test("shared fields associate each control with its own label and help", () => {
  const { ConfigField, ConfigTextInput, ConfigSelect } = loadComponent(resolve(root, "components/ui/config-field.tsx"));
  const html = renderToStaticMarkup(React.createElement(React.Fragment, null,
    React.createElement(ConfigField, { label: "Query", id: "query", note: "Search terms" },
      React.createElement(ConfigTextInput, { defaultValue: "malaria" })),
    React.createElement(ConfigField, { label: "Source", id: "source" },
      React.createElement(ConfigSelect, { value: "pubmed", options: [{ value: "pubmed", label: "PubMed" }], onChange: () => {} })),
  ));
  assert.match(html, /<label[^>]*id="query-label"[^>]*for="query"/);
  assert.match(html, /<input[^>]*id="query"[^>]*aria-labelledby="query-label"[^>]*aria-describedby="query-note"/);
  assert.match(html, /<div id="query-note">Search terms<\/div>/);
  assert.match(html, /<button[^>]*id="source"[^>]*aria-labelledby="source-label"/);
});

test("optional field help is named beside the label while essential guidance stays associated", () => {
  const { ConfigField, ConfigHelp, ConfigTextInput } = loadComponent(resolve(root, "components/ui/config-field.tsx"));
  const html = renderToStaticMarkup(React.createElement(ConfigField, {
    label: "Document type", id: "type", help: "Additional explanation",
    note: React.createElement(ConfigHelp, null, "Match the uploaded document."),
  }, React.createElement(ConfigTextInput)));
  assert.match(html, /aria-label="About Document type"/);
  assert.match(html, /aria-haspopup="dialog"/);
  assert.match(html, /aria-describedby="type-note"/);
  assert.match(html, /Match the uploaded document\./);
  assert.doesNotMatch(html, /Additional explanation|<details/);
  assert.ok(html.indexOf('aria-label="About Document type"') < html.indexOf('<input'));
});

test("result import stays available before configuration is complete but not during a run", () => {
  const { RunPanel } = loadComponent(resolve(root, "components/run-panel.tsx"));
  const render = (busy: boolean) => renderToStaticMarkup(React.createElement(RunPanel, {
    onRun: () => {}, onImport: () => {}, runDisabled: true, busy,
  }));
  assert.match(render(false), /accept="\.json,application\/json"/);
  assert.match(render(false), /<button(?![^>]* disabled="")[^>]*>Import result<\/button>/);
  assert.match(render(true), /<button[^>]*disabled=""[^>]*>Import result<\/button>/);
});

test("searchable fields retain the field label, selected value, help and disabled state", () => {
  const { ConfigField, ConfigSelect } = loadComponent(resolve(root, "components/ui/config-field.tsx"));
  const html = renderToStaticMarkup(React.createElement(ConfigField, {
    label: "Indication", id: "indication", note: "Context for this run",
  }, React.createElement(ConfigSelect, {
    value: "type_2_diabetes", options: [{ value: "type_2_diabetes", label: "Type 2 Diabetes" }],
    onChange: () => {}, searchLabel: "Search indications",
  })));
  assert.match(html, /<button[^>]*id="indication"/);
  assert.match(html, /aria-labelledby="indication-label [^"]+-value"/);
  assert.match(html, /aria-describedby="indication-note"/);
  assert.match(html, /aria-haspopup="dialog"/);
  assert.match(html, />Type 2 Diabetes<\/span>/);
  assert.doesNotMatch(html, /role="combobox"/); // Search input exists only when opened.
  const empty = renderToStaticMarkup(React.createElement(ConfigSelect, {
    value: undefined, options: [], onChange: () => {}, searchLabel: "Search indications",
  }));
  assert.match(empty, /disabled=""/);
});

test("an empty upload collection explains the next step and cannot run", () => {
  const { RunPanel } = loadComponent(resolve(root, "components/run-panel.tsx"));
  const html = renderToStaticMarkup(React.createElement(RunPanel, {
    documents: [], onRun: () => {}, emptyDocumentsHint: "Choose document types to add files.",
  }));
  assert.match(html, /Choose document types to add files\./);
  assert.match(html, /disabled=""/);
  const withSlot = renderToStaticMarkup(React.createElement(RunPanel, {
    documents: [{ id: "one", label: "Document" }], onRun: () => {},
    emptyDocumentsHint: "Choose document types to add files.",
  }));
  assert.doesNotMatch(withSlot, /Choose document types to add files\./);
  assert.match(withSlot, /Browse/);
});

test("PDF upload capability changes both the picker and its visible hint, not other tools", () => {
  const { RunPanel } = loadComponent(resolve(root, "components/run-panel.tsx"));
  const { TEXT_EXTRACTION_FORMATS } = loadComponent(resolve(root, "lib/document-formats.ts"));
  const ordinary = renderToStaticMarkup(React.createElement(RunPanel, { onRun: () => {} }));
  const screening = renderToStaticMarkup(React.createElement(RunPanel, {
    onRun: () => {}, documentFormats: TEXT_EXTRACTION_FORMATS,
  }));
  assert.match(ordinary, /accept="\.docx,\.pptx"/);
  assert.match(screening, /accept="\.docx,\.pptx,\.pdf"/);
  assert.match(screening, /DOCX, PPTX, PDF/);
  assert.match(screening, /Images are not read/);
  assert.doesNotMatch(ordinary, /Images are not read/);
});

test("extraction notice names affected documents and is absent for ordinary sources", () => {
  const { DocumentExtractionNotice } = loadComponent(resolve(root, "components/document-extraction-notice.tsx"));
  const block = { doc_id: "Trial report", structural_meta: { extraction_warnings: ["pdf_text_only"] } };
  const html = renderToStaticMarkup(React.createElement(DocumentExtractionNotice, { blocks: [block, block] }));
  assert.match(html, /aria-label="Document extraction limitations"/);
  assert.equal(html.match(/Trial report/g)?.length, 1);
  assert.match(html, /Images and scanned content are not read/);
  assert.equal(renderToStaticMarkup(React.createElement(DocumentExtractionNotice, {
    blocks: [{ doc_id: "Trial report", structural_meta: {} }],
  })), "");
});
