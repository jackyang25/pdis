import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { loadComponent } from "../test-support/load-component.ts";
import { EXTERNAL_TOOLS } from "./tools.ts";

const { ExternalToolCard } = loadComponent(
  fileURLToPath(new URL("../app/page.tsx", import.meta.url)), {}, ["ExternalToolCard"],
);

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
