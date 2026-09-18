import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { loadComponent } from "../test-support/load-component.ts";
import { CURRENT_RELEASE, RELEASES } from "./releases.ts";

const pagePath = fileURLToPath(new URL("../app/updates/page.tsx", import.meta.url));
const { default: UpdatesPage } = loadComponent(pagePath);
const { HeaderUtilities, FeedbackDetails } = loadComponent(
  fileURLToPath(new URL("../components/header-utilities.tsx", import.meta.url)), {}, ["FeedbackDetails"],
);

test("notes identify the running version without claiming deployment timing", () => {
  const html = renderToStaticMarkup(React.createElement(UpdatesPage));
  assert.equal((html.match(/<h1\b/g) ?? []).length, 1);
  assert.doesNotMatch(html, /<time\b|Unreleased|Not yet in production|Latest release/);
  assert.equal((html.match(/>This version</g) ?? []).length, 1);
  for (const release of RELEASES) {
    assert.ok(html.includes(`v${release.version}`));
    for (const section of release.sections) {
      if (section.title) assert.ok(html.includes(section.title));
      for (const change of section.changes) assert.ok(html.includes(change));
    }
  }
});

test("one build shows multiple versions with optional topic headings", () => {
  const releases = [
    { version: "0.5.0", title: "New capabilities", sections: [{ title: "Documents", changes: ["Improved coverage."] }] },
    { version: "0.4.1", title: "Corrections", sections: [{ changes: ["Fixed a display issue."] }] },
  ];
  const { default: Page } = loadComponent(pagePath,
    { "@/lib/releases": { CURRENT_RELEASE: releases[0], RELEASES: releases } });
  const html = renderToStaticMarkup(React.createElement(Page));
  assert.match(html, /Documents/);
  assert.match(html, /Improved coverage\./);
  assert.match(html, /Fixed a display issue\./);
  assert.ok(html.indexOf("v0.5.0") < html.indexOf("v0.4.1"));
  assert.equal((html.match(/>This version</g) ?? []).length, 1);
});

test("header identifies the bundled version and keeps feedback independent", () => {
  const html = renderToStaticMarkup(React.createElement(HeaderUtilities, { pathname: "/updates" }));
  const updatesLink = html.match(/<a\b[^>]*href="\/updates"[^>]*>/)?.[0];
  assert.ok(updatesLink);
  assert.match(updatesLink, /aria-current="page"/);
  assert.ok(html.includes(`What’s new — this version v${CURRENT_RELEASE.version}`));
  assert.match(html, /aria-label="Documentation"/);
  assert.match(html, /aria-label="Send feedback"/);
  const other = renderToStaticMarkup(React.createElement(HeaderUtilities, { pathname: "/scout" }));
  assert.doesNotMatch(other, /aria-current="page"/);
});

test("feedback directs readers to Teams without an email action or form", () => {
  const html = renderToStaticMarkup(React.createElement(FeedbackDetails));
  assert.match(html, /For feedback or requests, message Jack Yang or Shyam Bhaskaran on Teams\./);
  assert.doesNotMatch(html, /mailto:|@gatesfoundation\.org|<a\b|<form\b/);
});
