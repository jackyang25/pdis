import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { loadComponent } from "../test-support/load-component.ts";

const { FinalResultActions } = loadComponent(fileURLToPath(
  new URL("../components/final-result-actions.tsx", import.meta.url),
));

test("result download names the format without asserting completeness", () => {
  const html = renderToStaticMarkup(React.createElement(FinalResultActions, {
    onNewAnalysis: () => {}, download: { filename: "result.json", data: {} },
  }));
  assert.match(html, /Download JSON/);
  assert.doesNotMatch(html, /Download (final|partial) JSON/);
  const unavailable = renderToStaticMarkup(React.createElement(FinalResultActions, {
    onNewAnalysis: () => {},
  }));
  assert.doesNotMatch(unavailable, /Download JSON/);
});

const { ResultLayout } = loadComponent(fileURLToPath(
  new URL("../components/ui/result-layout.tsx", import.meta.url),
));
const { WarningNotice, ResultNotices } = loadComponent(fileURLToPath(
  new URL("../components/ui/warning-notice.tsx", import.meta.url),
));

test("shared warnings retain separate accessible labels and details", () => {
  const html = renderToStaticMarkup(React.createElement(ResultNotices, null,
    React.createElement(WarningNotice, { label: "Processing limitation" },
      React.createElement("details", null,
        React.createElement("summary", null, "Review unresolved fields"),
        "Original failure reason")),
    React.createElement(WarningNotice, { label: "Extraction limitation" }, "Missing visual"),
  ));
  assert.equal((html.match(/<aside /g) ?? []).length, 2);
  assert.match(html, /aria-label="Processing limitation"/);
  assert.match(html, /aria-label="Extraction limitation"/);
  assert.match(html, /<summary>Review unresolved fields<\/summary>Original failure reason/);
  assert.equal((html.match(/aria-hidden="true"/g) ?? []).length, 2);
  assert.equal((html.match(/rounded-lg border/g) ?? []).length, 2);
});

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

test("run-wide notices precede navigation and stay visible on every result tab", () => {
  for (const tabValue of ["findings", "trace"]) {
    const html = renderToStaticMarkup(React.createElement(ResultLayout, {
      title: "Example run", subtitle: "Document scope", metrics: "Totals", metricsNote: "Scope",
      tabValue, onTabChange: () => {}, tabs: "View navigation", children: "Result content",
      notices: React.createElement(React.Fragment, null,
        React.createElement("p", null, "Processing stopped"),
        React.createElement("p", null, "Visual not captured")),
    }));
    assert.ok(html.includes("Processing stopped"));
    assert.ok(html.indexOf("Document scope") < html.indexOf("Processing stopped"));
    assert.ok(html.indexOf("Processing stopped") < html.indexOf("Visual not captured"));
    assert.ok(html.indexOf("Visual not captured") < html.indexOf("View navigation"));
    assert.equal((html.match(/Processing stopped/g) ?? []).length, 1);
  }
});
