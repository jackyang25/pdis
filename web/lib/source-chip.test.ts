import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { loadComponent } from "../test-support/load-component.ts";
import { SOURCE_FORMATS } from "./api.ts";

const WEB = path.resolve(import.meta.dirname, "..");
const { PassageSource, SourceChip } = loadComponent(
  fileURLToPath(new URL("../components/ui/source-chip.tsx", import.meta.url)),
);

test("the web's file formats are the parser's", () => {
  // The parser records the format; the browser only translates it. A format added to the
  // parser and not here would render with no mark, as though it were unknown.
  const formats = readFileSync(path.join(WEB, "../services/chunker/formats.py"), "utf8");
  const declared = formats.match(/SourceFormat = Literal\[([^\]]+)\]/)?.[1];
  assert.ok(declared, "SourceFormat is no longer a Literal in formats.py");
  assert.deepEqual(
    [...declared.matchAll(/"([a-z]+)"/g)].map((match) => match[1]).sort(),
    [...SOURCE_FORMATS].sort(),
  );
});

test("a chip names its source's kind by what was recorded, never by inference", () => {
  const pptx = renderToStaticMarkup(createElement(SourceChip, { format: "pptx" }, "Slide 3"));
  assert.match(pptx, />PPTX</);
  assert.match(pptx, />Slide 3</);
  const web = renderToStaticMarkup(createElement(SourceChip, { format: "web" }, "cdc.gov"));
  assert.match(web, /lucide-globe/);
  // A block saved before the format was recorded says nothing about its type.
  const unknown = renderToStaticMarkup(createElement(SourceChip, { format: undefined }, "Page 2"));
  assert.match(unknown, /lucide-file-text/);
  assert.doesNotMatch(unknown, />(PDF|PPTX|DOCX|IMG)</);
});

test("a passage is named by its document, then where in it, and the location never gives way", () => {
  const html = renderToStaticMarkup(createElement(PassageSource, {
    format: "pptx", document: "2026 09 05 Truepoc SG2 [v20260905] PRESENTATION", location: "Slide 34",
  }));
  // A long file name truncates; "Slide 34" is the part a reader acts on, so it keeps its width.
  assert.match(html, /min-w-0[^"]*"[^>]*>(?:<span[^>]*>PPTX<\/span>)<span class="min-w-0 truncate">2026 09 05 Truepoc/);
  assert.match(html, /<span class="[^"]*shrink-0 whitespace-nowrap[^"]*">Slide 34<\/span>/);
  // Without a document, only the location; with neither, nothing.
  assert.doesNotMatch(renderToStaticMarkup(createElement(PassageSource, { format: "pdf", location: "Page 2" })), />PDF</);
  assert.equal(renderToStaticMarkup(createElement(PassageSource, { format: "pdf" })), "");
});

test("a chip is neutral, because colour carries findings", () => {
  const html = renderToStaticMarkup(createElement(SourceChip, { format: "pdf" }, "Plan"));
  assert.doesNotMatch(html, /tone-(danger|success|warning)|destructive/);
});

test("the citation shape is used only where a single source is named", () => {
  // "In document" opens a list, a source record carries a title and date, and a badge is a
  // category: each has its own component. A chip appearing anywhere else would blur what
  // this one means.
  const allowed = new Set([
    "components/ui/source-chip.tsx",
    "components/assistant/block-citation.tsx",
    "components/assistant/ask.tsx",
    "components/document-trace-panel.tsx",
  ]);
  const sources = (directory: string): string[] =>
    readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
      const full = path.join(directory, entry.name);
      if (entry.isDirectory()) return sources(full);
      return entry.name.endsWith(".tsx") && !entry.name.includes(".test.") ? [full] : [];
    });
  const users = [...sources(path.join(WEB, "app")), ...sources(path.join(WEB, "components"))]
    .filter((file) => /<SourceChip\b|function SourceChip\b/.test(readFileSync(file, "utf8")))
    .map((file) => path.relative(WEB, file));
  assert.deepEqual(users.filter((file) => !allowed.has(file)), []);
});
