/**
 * Every tool's final result exports to Word and Excel the same way: the `fileExport` action
 * beside its JSON download, through the one `ResultExportMenu`. A tool given its own export
 * control, or none, is the drift this pins.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";

const WEB = path.resolve(import.meta.dirname, "..");

for (const tool of ["inspector", "aligner", "screener", "scout", "drafter"] as const) {
  test(`${tool} offers its final result as a Word or Excel file beside the JSON`, () => {
    const page = readFileSync(path.join(WEB, "app", tool, "page.tsx"), "utf8");
    const actions = page.slice(page.indexOf("<FinalResultActions"));
    assert.match(actions.slice(0, actions.indexOf("/>")), new RegExp(`fileExport=\\{[\\s\\S]*tool: "${tool}"`));
    assert.doesNotMatch(page, /Export(Button|Menu)\b/, `${tool} draws its own export control`);
  });
}

test("the result bar offers one Export menu for Word and Excel, beside the JSON download", async () => {
  const React = await import("react");
  const { renderToStaticMarkup } = await import("react-dom/server");
  const { loadComponent } = await import("../test-support/load-component.ts");
  const { FinalResultActions } = loadComponent(path.join(WEB, "components/final-result-actions.tsx"), {
    "@/lib/api": { exportResultFile: async () => ({ blob: new Blob(), filename: "x" }) },
  });
  const html = renderToStaticMarkup(React.createElement(FinalResultActions, {
    onNewAnalysis: () => {},
    download: { filename: "pdis-aligner.json", data: () => ({}) },
    fileExport: { tool: "aligner", result: { blocks: [] }, onError: () => {} },
  }));
  assert.match(html, /Download JSON/);
  // One control that opens the formats, not a button per format.
  assert.match(html, /aria-haspopup="dialog"[^>]*>[\s\S]*?Export[\s\S]*?<\/button>/);
  assert.doesNotMatch(html, /Export to Word/);
});
