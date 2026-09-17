import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { loadComponent } from "../test-support/load-component.ts";

const { ResultLayout } = loadComponent(fileURLToPath(
  new URL("../components/ui/result-layout.tsx", import.meta.url),
));

test("result views show one AI disclaimer in the header, before navigation", () => {
  for (const tabValue of ["findings", "trace"]) {
    const html = renderToStaticMarkup(React.createElement(ResultLayout, {
      title: "Example run",
      subtitle: "Document scope",
      metrics: "Run totals",
      metricsNote: "What was assessed",
      tabValue,
      onTabChange: () => {},
      tabs: React.createElement("span", null, "View navigation"),
      scopeControl: React.createElement("span", null, "Rubric selector"),
      children: React.createElement("aside", null, "Specific extraction limitation"),
    }));
    assert.equal((html.match(/AI-generated results/g) ?? []).length, 1);
    const note = html.indexOf("AI-generated results");
    assert.ok(note > html.indexOf("Document scope"));
    assert.ok(note < html.indexOf("</header>"));
    assert.ok(note < html.indexOf("Rubric selector"));
    assert.ok(note < html.indexOf("View navigation"));
    assert.match(html, /Verify findings against the cited sources and original documents before making decisions\./);
    assert.match(html, /Specific extraction limitation/);
  }
});
