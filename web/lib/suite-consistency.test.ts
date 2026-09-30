/**
 * Shapes every tool shares, checked where a page could quietly write its own.
 *
 * Each of these drifted once: a tool drew its own copy, the copy lost one detail, and the
 * suite looked assembled from parts. A shared component fixes the copies that exist; these
 * keep a new one from appearing.
 */

import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";

const WEB = path.resolve(import.meta.dirname, "..");
const TOOL_PAGES = ["inspector", "aligner", "screener", "scout", "chunker", "searcher"]
  .map((tool) => path.join(WEB, "app", tool, "page.tsx"));

function sources(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(directory, entry.name);
    if (entry.isDirectory()) return sources(full);
    return entry.name.endsWith(".tsx") && !entry.name.includes(".test.") ? [full] : [];
  });
}

test("cards on a tool page share one side inset", () => {
  // `px-5 sm:px-6` on every card and band. Scout's review checkpoint used 28px, so its
  // content sat 4px inside the run panel above it and the result card below.
  const offenders = [...TOOL_PAGES, ...sources(path.join(WEB, "components")).filter((file) =>
    !/(app-shell|assistant|docs|document-trace-viewer)/.test(file))]
    .flatMap((file) => (readFileSync(file, "utf8").match(/\bsm:px?-7\b/g) ?? [])
      .map((match) => `${path.relative(WEB, file)}: ${match}`));
  assert.deepEqual(offenders, []);
});

test("starting again is one button", () => {
  // A result header and each Scout review checkpoint drew their own, and only one carried
  // the icon that matches Metrics beside it.
  const offenders = TOOL_PAGES
    .filter((file) => />\s*New analysis\s*</.test(readFileSync(file, "utf8")))
    .map((file) => path.relative(WEB, file));
  assert.deepEqual(offenders, []);
});

test("a panel's close control sits on its heading, not in a bar of its own", async () => {
  const { createElement: h } = await import("react");
  const { renderToStaticMarkup } = await import("react-dom/server");
  const { loadComponent } = await import("../test-support/load-component.ts");
  const { TracePanelHeader, TracePanelCloseProvider } = loadComponent(path.join(WEB, "components", "document-trace-panel.tsx"));
  const close = h("button", { "aria-label": "Close trace details" });
  const inherited = renderToStaticMarkup(h(TracePanelCloseProvider, { value: close }, h(TracePanelHeader, { eyebrow: "Insufficient", title: "Presentation" })));
  assert.match(inherited, /<header[\s\S]*Presentation[\s\S]*aria-label="Close trace details"[\s\S]*<\/header>/);
  const explicit = renderToStaticMarkup(h(TracePanelCloseProvider, { value: close }, h(TracePanelHeader, { eyebrow: "Source passage", title: "Uploaded document", action: h("button", { "aria-label": "Close source passages" }) })));
  assert.doesNotMatch(explicit, /Close trace details/);
  // The viewer no longer draws a close bar above the panel.
  const viewer = readFileSync(path.join(WEB, "components", "document-trace-viewer.tsx"), "utf8");
  assert.doesNotMatch(viewer, /flex justify-end border-b border-border\/80 px-2 py-2/);
});
