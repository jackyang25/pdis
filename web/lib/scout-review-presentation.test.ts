import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { loadComponent } from "../test-support/load-component.ts";
import { TONE_TINT } from "./tone.ts";

const { ReviewListRow } = loadComponent(
  fileURLToPath(new URL("../app/scout/page.tsx", import.meta.url)), {}, ["ReviewListRow"],
);

test("review rows preserve shared status tones independently of selection", () => {
  for (const [tone, label, sharedTone] of [
    ["positive", "Admitted", "success"],
    ["warning", "Needs review", "warning"],
    ["neutral", "Rejected", "neutral"],
  ] as const) {
    for (const selected of [false, true]) {
      const html = renderToStaticMarkup(React.createElement(ReviewListRow, {
        tone, status: label, selected, onSelect: () => {},
        title: "Document target", subtitle: "24 months", detail: "Cited evidence",
      }));
      const status = html.match(new RegExp(`<span[^>]*class="([^"]*)"[^>]*>${label}</span>`));
      assert.ok(status, `Visible ${label} status`);
      for (const token of TONE_TINT[sharedTone].split(" ")) {
        assert.ok(status[1].split(" ").includes(token), `${label} uses shared ${sharedTone} treatment`);
      }
      assert.equal(html.includes('aria-current="true"'), selected);
    }
  }
});
