import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { loadComponent } from "../test-support/load-component.ts";
import { EXTERNAL_TOOLS, WORKSPACE_TOOLS } from "./tools.ts";

const { ExternalToolCard } = loadComponent(
  fileURLToPath(new URL("../app/page.tsx", import.meta.url)), {}, ["ExternalToolCard"],
);

const { WorkspaceToolCard } = loadComponent(
  fileURLToPath(new URL("../app/page.tsx", import.meta.url)), {}, ["WorkspaceToolCard"],
);

test("workspace cards show run status without changing their navigation", () => {
  const tool = WORKSPACE_TOOLS.find(tool => tool.id === "inspector")!;
  for (const status of ["Waiting for capacity", "Running", "Ready for review", "Results available"]) {
    const html = renderToStaticMarkup(React.createElement(WorkspaceToolCard, { tool, status }));
    assert.ok(html.includes(status));
    assert.ok(!html.includes(tool.activity!), "active status replaces the idle estimate");
    assert.match(html, /href="\/inspector"/);
    assert.equal((html.match(/<a\b/g) ?? []).length, 1);
    assert.doesNotMatch(html, /<button\b/);
  }
});

test("only running cards show the decorative pixel-grid loader", () => {
  const tool = WORKSPACE_TOOLS.find(tool => tool.id === "scout")!;
  for (const status of [null, "Waiting for capacity", "Running", "Ready for review", "Results available"]) {
    const html = renderToStaticMarkup(React.createElement(WorkspaceToolCard, { tool, status }));
    assert.equal((html.match(/motion-safe:animate-pixel-wave/g) ?? []).length, status === "Running" ? 9 : 0);
    assert.doesNotMatch(html, /<video\b|shimmer/);
  }
});

test("an idle workspace card has no status label and retains its duration", () => {
  const tool = WORKSPACE_TOOLS.find(tool => tool.id === "inspector")!;
  const html = renderToStaticMarkup(React.createElement(WorkspaceToolCard, { tool }));
  assert.doesNotMatch(html, /Running|Waiting for capacity|Ready for review|Results available/);
  assert.ok(html.includes(tool.activity!));
  assert.match(html, /role="status"/);
});

test("external workflow actions name the destination without making the container a link", () => {
  for (const tool of EXTERNAL_TOOLS.filter(tool => tool.availability === "available")) {
    const html = renderToStaticMarkup(React.createElement(ExternalToolCard, { tool }));
    assert.match(html, /^<article\b/);
    assert.equal((html.match(/<a\b/g) ?? []).length, tool.shortcuts.length);
    for (const shortcut of tool.shortcuts) {
      assert.ok(html.includes(`Open in ${shortcut.label}`));
      assert.ok(html.includes(`href="${shortcut.url.replaceAll("&", "&amp;")}"`));
    }
  }
});
