import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { loadComponent } from "../test-support/load-component.ts";
import { CURRENT_RELEASE, RELEASES, UNRELEASED_CHANGES } from "./releases.ts";

const { default: UpdatesPage } = loadComponent(fileURLToPath(new URL("../app/updates/page.tsx", import.meta.url)));
const { HeaderUtilities, FeedbackDetails } = loadComponent(
  fileURLToPath(new URL("../components/header-utilities.tsx", import.meta.url)), {}, ["FeedbackDetails"],
);

test("release notes distinguish pending changes from dated published releases", () => {
  const html = renderToStaticMarkup(React.createElement(UpdatesPage));
  assert.equal((html.match(/<h1\b/g) ?? []).length, 1);
  assert.equal((html.match(/<time\b/g) ?? []).length, RELEASES.length);
  assert.match(html, /Unreleased/);
  assert.match(html, /Not yet in production/);
  assert.ok(html.indexOf("Unreleased") < html.indexOf(`v${CURRENT_RELEASE.version}`));
  for (const release of RELEASES) {
    assert.ok(html.includes(`dateTime="${release.releasedAt}"`));
    assert.ok(html.includes(`v${release.version}`));
    for (const change of release.changes) assert.ok(html.includes(change));
  }
  for (const change of UNRELEASED_CHANGES) assert.ok(html.includes(change));
});

test("header keeps feedback independent and marks the active updates destination", () => {
  const html = renderToStaticMarkup(React.createElement(HeaderUtilities, { pathname: "/updates" }));
  const updatesLink = html.match(/<a\b[^>]*href="\/updates"[^>]*>/)?.[0];
  assert.ok(updatesLink);
  assert.match(updatesLink, /aria-current="page"/);
  assert.match(html, /aria-label="What’s new/);
  assert.match(html, /aria-label="Documentation"/);
  assert.match(html, /aria-label="Send feedback"/);
  assert.ok(html.includes(`v${CURRENT_RELEASE.version}`));
  const otherPage = renderToStaticMarkup(React.createElement(HeaderUtilities, { pathname: "/scout" }));
  assert.doesNotMatch(otherPage, /aria-current="page"/);
});

test("feedback directs readers to Teams without an email action or form", () => {
  const html = renderToStaticMarkup(React.createElement(FeedbackDetails));
  assert.match(html, /For feedback or requests, message Jack Yang or Shyam Bhaskaran on Teams\./);
  assert.doesNotMatch(html, /mailto:|@gatesfoundation\.org|<a\b|<form\b/);
});
